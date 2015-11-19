__author__ = 'frank'

import logging
import logging.handlers

fileLogger = logging.handlers.RotatingFileHandler("logs/FrankFancyStreamer.log", maxBytes=1e6, backupCount=25)
fileLogger.setFormatter(logging.Formatter(fmt='%(asctime)s\t%(levelname)s: %(message)s', datefmt='(%d-%m)%H:%M:S'))

consoleLogger = logging.StreamHandler()
consoleLogger.setFormatter(logging.Formatter(fmt='%(asctime)s\t%(levelname)s: %(message)s', datefmt='(%d-%m)%H:%M:S'))

for loggerName in ['FrankFancyStreamer']:
	l = logging.getLogger(loggerName)
	l.addHandler(consoleLogger)
	l.addHandler(fileLogger)