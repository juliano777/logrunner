#!/usr/bin/env python
#########################################################################
##
##  LogRunner
##  Copyright (C) 2013 Jacob Cook
##  jacob@jcook.cc
##
##  This program is free software: you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation, either version 3 of the License, or
##  (at your option) any later version.
##
##  This program is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##  GNU General Public License for more details.
##
##  You should have received a copy of the GNU General Public License
##  along with this program.  If not, see <http://www.gnu.org/licenses/>.
##
#########################################################################

import atexit
import configparser
import gzip
import os
import signal
import subprocess
import sys
import time
import logging
import tempfile
import shutil


class LogRunner:
	def __init__(self, config_file, logmethod):
		# Create the ramdisk and move any prior logs to memory
		self.stoploop = False
		logging.basicConfig(
			format='%(asctime)s [%(levelname)s] - %(message)s',
			datefmt='%Y-%m-%d %H:%M:%S',
			level=logging.INFO,
			filename=('/var/log/logrunner.log' if logmethod is 'tofile' else ''),
			)
		logging.info('Initializing LogRunner')

		cfg = configparser.SafeConfigParser()

		if os.path.exists(config_file):
			cfg.read(config_file)
		else:
			cfg.add_section('config')
			cfg.add_section('ignore')

			cfg.set('config', 'size', '1024')
			cfg.set('config', 'ramsize', '16')
			cfg.set('config', 'path', '/var/log')
			cfg.set('config', 'gzpath', '/var/logstore')
			cfg.set('ignore', 'folders', 'journal,sa')
			cfg.set('ignore', 'files', 'lastlog,faillog')
			logging.warning("Couldn't find the config file. Using defaults.")

		self.size = cfg.getint('config', 'size') * 1024
		self.ramsize = cfg.getint('config', 'ramsize') * 1048576
		self.path = cfg.get('config', 'path')
		self.gzpath = cfg.get('config', 'gzpath')
		self.igfolds = cfg.get('ignore', 'folders').split(',')
		self.igfiles = cfg.get('ignore', 'files').split(',')

		self.logmount = tempfile.mkdtemp()
		try:
			subprocess.call(['mount', '-t', 'tmpfs', '-o',
				'nosuid,noexec,nodev,mode=0755,size={}'.format(self.ramsize),
				'logrunner',
				self.logmount])
		except Exception as e:
			logging.error(e)
			logging.critical('Creation of ramdisk/mount failed, exiting')
			sys.exit(1)

		if not os.path.isdir(self.path):
			os.mkdir(self.path, mode=0o0754)

		if not os.path.isdir(self.gzpath):
			os.mkdir(self.gzpath, mode=0o0754)

		for item in os.listdir(self.path):
			path = os.path.join(self.path, item)
			if os.path.isdir(path):
				shutil.copytree(path, os.path.join(self.logmount, item))
			else:
				if '.gz' in item:
					shutil.move(path, os.path.join(self.gzpath, item))
				else:
					shutil.copy2(path, self.logmount)

		subprocess.call(['mount', '--bind', self.path, self.logmount])

		# Normal exit when terminated
		atexit.register(self.stop)
		signal.signal(signal.SIGTERM, lambda signum, stack_frame: sys.exit(0))
		signal.signal(signal.SIGINT, lambda signum, stack_frame: sys.exit(0))

		logging.info('LogRunner is up and hunting for replicants')

		while self.stoploop == False:
			for path, dirs, files in os.walk(self.path):
				if not any(x in path for x in self.igfolds):
					for logfile in files:
						if not any(x in logfile for x in self.igfiles):
							self.check(os.path.join(path, logfile))
			time.sleep(60)

	def retire(self, logfile):
		# Write the log to backup location, and flush memory
		absin = os.path.join(self.path, logfile)
		absout = os.path.join(self.gzpath, logfile + '.gz')
		login = open(absin, 'rb')

		limit = 5
		mvfiles = []
		for x in range(0, limit):
			path = absout if x == 0 else '.'.join((absout, x))

			if not os.path.exists(path):
				break

			mvfiles.append((x, path, '.'.join((absout, x + 1))))

		for i, path, nextpath in mvfiles:
			if i == 0:
				shutil.rm(path)
			else:
				shutil.move(path, nextpath)

		if not os.path.exists(os.path.dirname(absout)):
			os.makedirs(os.path.dirname(absout))
		try:
			logout = gzip.open(absout, 'wb')
			logout.writelines(login)
			logout.close()
			login.close()
		except Exception as e:
			logging.error(e)
			logging.error('Couldn\'t backup the file %s, whoops' % absin)
		else:
			logging.info('%s retired to %s' % (absin, absout))
		open(absin, 'w').close()

	def check(self, logfile):
		# Check memory use. If too high, force log write and flush.
		if os.path.getsize(logfile) >= self.size:
			self.retire(logfile.split(self.path, 1)[1].lstrip('/'))

	def stop(self):
		# Unmount everything and stop operation
		self.stoploop = True
		subprocess.call(['umount', self.logmount])
		for item in os.listdir(self.logmount):
			path = os.path.join(self.logmount, item)
			if os.path.isdir(path):
				if os.path.exists(os.path.join(self.path, item)):
					shutil.rmtree(os.path.join(self.path, item))
				shutil.copytree(path, os.path.join(self.path, item))
			else:
				shutil.copy2(path, self.path)

		subprocess.call(['umount', 'logrunner'])
		shutil.rmtree(self.logmount)
		logging.info('LogRunner stopped successfully')
		sys.exit(0)
