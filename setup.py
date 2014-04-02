from setuptools import setup

setup(name='ical-reminder',
      version='0.1',
      description='Standalone iCal reminder tool',
      author='Dan Smith',
      author_email='dsmith@danplanet.com',
      url='http://github.com/kk7ds/ical-reminder',
      license='GPLv3',
      packages=['ical_reminder'],
      install_requires=['icalendar'],
      )
