# _*_ coding: utf-8 _*_
#
# This script creates a named pipe (if it doesn't exist)
# and writes the feed name, article title and url to it
# whenever an article is saved to the database. 
#
# This is useful for composing systems that constantly read
# the FIFO and do things like emit the data to IRC channels.
#
# You could, for instance, perform fuzzy pattern matching and be
# notified when certain keywords are in the news.
#
# Transmission to a natural language processing/translation service
# can also be done in a script or by reading a FIFO like the one here.
#
# Whether you use this system to profit, perform intelligence analysis
# or inform your next vote is hopefully up to you!
#
# Luke Brooks, 2015
# MIT License
# Many big thanks to God, lord of universes.
fifo = "/tmp/harvest.pipe"

import os
if not os.path.exists(fifo):
	try:
		os.mkfifo(fifo)
	except Exception as e:
		cache['app'].log("Error creating %s: %s" % (fifo, str(e)))

# Harvest always executes scripts with an article and its feed in the namespace.

# There is also a dictionary named cache, containing the app object.
# Through the app object you can access the logging interface and the feed manager.
try:
	# READER BEWARE: Use non-blocking IO or you won't be storing owt.
	fd = os.open(fifo, os.O_CREAT | os.O_WRONLY | os.O_NONBLOCK)
	os.write(fd, ("%s: %s\n%s\n" % (feed.name, article.title, article.url)).encode())
	os.close(fd)
	del fd
except Exception as e: # Usually due to there not being a reader fd known to the kernel.
	pass

del os, fifo
