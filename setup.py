#!/usr/bin/env python3

from distutils.core import setup

setup(name='logrunner',
      version='0.1',
      description='Stores logs in memory and intelligently writes to disk',
      author='Jacob Cook',
      author_email='jacob@jcook.cc',
      url='http://jcook.cc/logrunner',
      packages=['logrunner'],
      scripts=['logrunnerd'],
      data_files=[
      ('/etc', ['logrunner.conf']),
      ('/usr/lib/systemd/system', ['logrunner.service']),
      ]
     )
