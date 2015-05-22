import base64
import codecs
import datetime
import iso8601
import icalendar
import pytz
import subprocess
import sys
import time
import urllib2


UTC = iso8601.iso8601.Utc()
LOCAL = pytz.timezone('America/Los_Angeles')


def get_now():
    return datetime.datetime.utcnow().replace(tzinfo=UTC)


def get_exceptions(event):
    try:
        exceptions = event.decoded('EXDATE')
    except KeyError:
        return []

    if not isinstance(exceptions, list):
        exceptions = [exceptions]

    exception_dates = []
    for ex in exceptions:
        try:
            tz = pytz.timezone(ex.params['TZID'])
        except:
            tz = UTC
        dates = [dt.dt.replace(tzinfo=tz) for dt in ex.dts]
        exception_dates.extend(dates)

    return exception_dates


def get_repeat_event(event):
    start = event.decoded('DTSTART').astimezone(UTC)
    now = datetime.datetime.utcnow().replace(tzinfo=UTC)
    delta = now - start
    exceptions = get_exceptions(event)
    try:
        rule = event.decoded('RRULE')
    except KeyError:
        return start
    if rule.get('freq') == ['WEEKLY']:
        try:
            day = rule.get('byday')
        except KeyError:
            day = None
        interval = rule.get('interval', [1])

        if not day and not interval:
            print 'No interval or day for %s' % event.get('summary')
            return start
        elif interval:
            offset = interval[0] * 7
        elif day:
            offset = 7
    elif rule.get('freq') == ['DAILY']:
        try:
            offset = rule.get('interval')[0]
        except:
            print 'Failed to decode %s for %s' % (
                rule, event.get('summary'))
            return start
    else:
        print 'Unsupported repeat rule %s for %s' % (
            rule, event.get('summary'))
        return start

    correction = delta.days / offset
    correction += delta.days % offset and 1 or 0
    repeat = start + datetime.timedelta(days=(correction * offset))

    for exception in exceptions:
        if exception.astimezone(UTC) == repeat:
            # This repeat is canceled
            print '%s: instance %s is canceled' % (event.get('summary'),
                                                   repeat)
            return start
    return repeat


class AlarmContext(object):
    def __init__(self):
        self._alarms = {}

    def register(self, alarm):
        if (alarm.id not in self._alarms or
                (self._alarms[alarm.id] and
                 alarm.due >= self._alarms[alarm.id])):
            self._alarms[alarm.id] = alarm.due
        return self._alarms[alarm.id]

    def update(self, alarm):
        self._alarms[alarm.id] = alarm.due

    def get(self, alarm_id):
        return self._alarms[alarm_id]

    def has_alarm(self, alarm_id):
        return alarm_id in self._alarms


class Alarm(object):
    def __init__(self, event, alarm, next_repeat, context):
        self._event = event
        self._alarm = alarm
        self._fire_at = next_repeat + alarm.decoded('TRIGGER')
        self._event_instance = next_repeat
        self._context = context
        # Update our due date from the context, if present
        self._fire_at = self._context.register(self)

    @property
    def id(self):
        # FIXME for multiple alarms!
        return '%s_%s' % (self._event.get('UID'),
                          self._event_instance)

    @property
    def is_due(self):
        if not self._fire_at:
            return False
        now = get_now()
        return now > self._fire_at

    @property
    def due(self):
        return self._fire_at

    def __str__(self):
        return '%s: %s' % (
            self._fire_at and self._fire_at.astimezone(LOCAL) or 'Disabled',
            self._event.get('summary'))

    def snooze(self, minutes):
        self._fire_at = get_now() + datetime.timedelta(minutes=minutes)
        self._context.register(self)

    def acknowledge(self):
        self._fire_at = None
        self._context.update(self)

    @classmethod
    def get_from_event(cls, event, next_repeat, context):
        alarms = []
        for item in event.walk():
            if item.name == 'VALARM':
                alarms.append(cls(event, item, next_repeat, context))
        return alarms


class Event(object):
    def __init__(self, event, context):
        self._context = context
        self._event = event
        self._next_repeat = get_repeat_event(event)
        self._alarms = Alarm.get_from_event(event, self._next_repeat, context)

    def process_change(self, event):
        recurrence = event.get('recurrence-id')
        if recurrence and recurrence.dt == self._next_repeat:
            orig = self._next_repeat
            self._next_repeat = event.decoded('dtstart')
            self._alarms = Alarm.get_from_event(event, self._next_repeat,
                                                self._context)
            print "%s: %s rescheduled to %s" % (event.get('summary'),
                                                orig,
                                                self._next_repeat)
        elif not recurrence:
            print "Unknown change %s @ %s" % (event.get('summary'),
                                              event.decoded('dtstart'))

    @property
    def uid(self):
        return self._event.get('uid')

    @property
    def summary(self):
        return self._event.get('summary')

    @property
    def description(self):
        return self._event.get('description')

    @property
    def location(self):
        return self._event.get('location')

    @property
    def start_time(self):
        return self._next_repeat.astimezone(LOCAL)

    @property
    def has_alarms(self):
        return bool(self._alarms)

    @property
    def alarms(self):
        return self._alarms

    @property
    def is_relevant(self):
        return self._next_repeat > get_now()


class Calendar(object):
    def __init__(self, config):
        self._context = AlarmContext()
        self._config = config
        self.read_config()

    def read_config(self):
        print 'Reading config'
        config_file = self._config.get('state', 'config_file', 'reminder.conf')
        self._config.read(config_file)

    def _process_event(self, upcoming, item):
        if item.get('recurrence-id'):
            for event in upcoming:
                if event.uid == item.get('uid'):
                    event.process_change(item)
                    return event
            print 'No event matching recurrence %s' % item.get('summary')
        return Event(item, self._context)

    def _get_upcoming(self, cal, timerange):
        upcoming = []
        for item in cal.walk():
            if item.name == 'VEVENT':
                start = item.decoded('DTSTART')
                if isinstance(start, datetime.datetime):
                    pass
                elif isinstance(start, datetime.date):
                    # Convert this to start-of-day localtime!
                    continue

                try:
                    event = self._process_event(upcoming, item)
                except:
                    print 'Failed to parse %s' % item.get('summary')
                    continue
                if (event.is_relevant and event.has_alarms and
                        event not in upcoming):
                    upcoming.append(event)
        print 'Upcoming'
        for event in sorted(upcoming, key=lambda x: x._next_repeat):
            for alarm in event.alarms:
                print alarm

        return upcoming

    def _get_calendar_data(self, url, username, password):
        req = urllib2.Request(url)
        if username:
            auth = base64.encodestring('%s:%s' % (username, password))
            auth = auth.replace('\n', '')
            req.add_header('Authorization', 'Basic %s' % auth)
        con = urllib2.urlopen(req)
        return con.read()

    def _refresh_calendar_caldav(self):
        import caldav
        import caldav.objects
        client = caldav.DAVClient(
            url=self._config.get('calendar', 'url'),
            username=self._config.get('calendar', 'user'),
            password=self._config.get('calendar', 'pass'))
        calendar = caldav.objects.Calendar(
            client=client, 
            url=self._config.get('calendar', 'url'))

        self._cal = icalendar.Calendar()

        for event in calendar.events():
            if type(event.data) == unicode:
                event_data = event.data
            else:
                event_data = codecs.decode(event.data, 'utf8')

            cal = icalendar.Calendar.from_ical(event_data)
            for component in cal.subcomponents:
                self._cal.add_component(component)

        with codecs.open('calendar.ics', 'w', encoding='utf-8') as f:
            f.write(codecs.decode(self._cal.to_ical(), 'utf-8'))
        self._upcoming_events = self._get_upcoming(self._cal,
                                                   datetime.timedelta(days=2))
        self._last_refresh = datetime.datetime.now()

    def _refresh_calendar_ical(self):
        data = self._get_calendar_data(
            self._config.get('calendar', 'url'),
            self._config.get('calendar', 'user'),
            self._config.get('calendar', 'pass'))
        with file('calendar.ics', 'w') as f:
            f.write(data)
        self._cal = icalendar.Calendar.from_ical(data)
        self._upcoming_events = self._get_upcoming(self._cal,
                                                   datetime.timedelta(days=2))
        self._last_refresh = datetime.datetime.now()

    def refresh_calendar(self):
        if self._config.get('calendar', 'caldav'):
            self._refresh_calendar_caldav()
        else:
            self._refresh_calendar_ical()

    def handle_alarm(self, event, alarm):
        print '*** Alarm: %s' % event.summary
        print '  Starts at: %s' % event.start_time
        print '  Alarm due: %s' % alarm.due
        print ''
        answer = 'h'
        while answer not in 'sSaA':
            print '(S)nooze for 5 Minutes, (A)cknowledge > ',
            answer = sys.stdin.read().strip()
        if answer.lower() == 'a':
            alarm.acknowledge()
        elif answer.lower() == 's':
            alarm.snooze(5)
            print 'New due date: %s' % alarm.due

    def calendar_age(self):
        return datetime.datetime.now() - self._last_refresh

    def handle_alarms_until_refresh(self):
        mins = self._config.getint('calendar', 'refresh')
        while self.calendar_age() < datetime.timedelta(minutes=mins):
            for event in self._upcoming_events:
                for alarm in event.alarms:
                    if alarm.is_due:
                        self.handle_alarm(event, alarm)
            time.sleep(self._config.getint('alarms', 'poll'))


class ZenityCalendar(Calendar):
    """A really hacky alarm pop-up using Zenity to do the dirty work"""
    def handle_alarm(self, event, alarm):
        msg = '%s\nSnooze?' % event.summary
        dismiss = subprocess.call(['zenity', '--question', '--text', msg])
        if dismiss:
            alarm.acknowledge()
        else:
            msg = 'Snooze minutes:'
            default = self._config.get('alarms', 'default_snooze')
            try:
                snooze = subprocess.check_output(['zenity', '--entry',
                                                  '--text', msg,
                                                  '--entry-text', default])
                snooze = int(snooze)
            except subprocess.CalledProcessError:
                snooze = 0
            except ValueError:
                # This will cause this to show up again on the next poll
                return
            if snooze is 0:
                alarm.acknowledge()
            else:
                alarm.snooze(snooze)
        print 'Alarm now due: %s' % alarm.due


class GtkCalendar(Calendar):
    def handle_alarm(self, event, alarm):
        from ical_reminder import dialog
        dialog.run_one(event, alarm)
