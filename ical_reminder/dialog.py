from gi.repository import Gtk


class Reminder(Gtk.Dialog):
    def __init__(self, event, alarm):
        title = '%s: %s' % (event.start_time.strftime('%m/%d @ %H:%M'),
                            event.summary)
        Gtk.Dialog.__init__(self, title)

        self.set_default_size(500, 300)

        vbox = self.get_content_area()
        hbox = self.get_action_area()

        self.title_label = Gtk.Label()
        self.title_label.set_markup('<big><b>%s</b></big>' % event.summary)
        vbox.add(self.title_label)

        self.detail_label = Gtk.Label(
            event.start_time.strftime('%H:%M (%m-%d-%Y)'))
        vbox.add(self.detail_label)

        description = Gtk.TextView()
        description.set_wrap_mode(Gtk.WrapMode.WORD)
        description.get_buffer().set_text(
            'Location: %s\n\n%s' % (
                event.location, event.description))
        description.set_editable(False)
        description.set_cursor_visible(False)
        sw = Gtk.ScrolledWindow()
        sw.add(description)
        vbox.pack_start(sw, True, True, 0)

        dismiss = Gtk.Button(label='Dismiss')
        dismiss.connect('clicked', lambda w: self._dismiss(alarm))
        hbox.add(dismiss)

        snooze = Gtk.Button(label='Snooze')
        snooze.connect('clicked',
                       lambda w: self._snooze(alarm, snoozetimes.get_active()))
        hbox.add(snooze)

        self._snooze_times = [('5 Minutes', 5), ('10 Minutes', 10),
                              ('15 Minutes', 15), ('30 Minutes', 30),
                              ('1 Hour', 60), ('2 Hours', 120),
                              ('6 Hours', 360), ('12 Hours', 720),
                              ('1 Day', (24 * 60)), ('2 Days', (48 * 60))]

        snoozetimes = Gtk.ComboBoxText.new()
        for label, minutes in self._snooze_times:
            snoozetimes.append(None, label)
        snoozetimes.set_active(0)
        hbox.add(snoozetimes)

    def _dismiss(self, alarm):
        alarm.acknowledge()
        self.destroy()

    def _snooze(self, alarm, index):
        alarm.snooze(self._snooze_times[index][1])
        self.destroy()


def run_one(event, alarm):
    def auto_dismiss(window, event, alarm):
        alarm.acknowledge()

    window = Reminder(event, alarm)
    window.connect('delete-event', auto_dismiss, alarm)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()

if __name__ == '__main__':
    import datetime

    class Event(object):
        pass

    class Alarm(object):
        def snooze(self, minutes):
            print 'SNOOZED %s minutes' % minutes

        def acknowledge(self):
            print 'ACKED'

    event = Event()
    event.start_time = datetime.datetime.now()
    event.summary = 'Test Event'
    event.location = 'Test Location'
    event.description = ('Loooooooooooooooooooots\nOf\nDetails!\n' +
                         'this will become a very long line which ' +
                         'will help test that the wrapping mode is ' +
                         'correctly set on the text view.')

    alarm = Alarm()

    run_one(event, alarm)
