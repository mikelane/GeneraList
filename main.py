#!/usr/bin/env python

"""
GeneraList lets you use Amazon's Alexa to create and use lists that hold any type of data.

Ask GeneraList to store grocery items as you think of them during the week and then access those items when
you're on the go at the supermarket. Or give generalist a list of instructions that Alexa can read off to
you later as you ask her to. Have a recipe that you love? Let GeneraList read the instructions to you as
you're cooking.

To add: Music Playlists, Video Playlists, Lists of slides for a slideshow. These will require Alexa to
interact with other web services.
"""

__author__ = "Mike Lane"
__copyright__ = "Copyright 2016, Michael Lane"
__license__ = "GPL"
__version__ = "3.0"
__email__ = "mikelane@gmail.com"

from __future__ import print_function
import json
import boto3

