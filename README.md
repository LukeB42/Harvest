Harvest
=======

An intelligence utility / test for researchers, programmers and generally carnivorous primates who want personally curated news archives.
Harvest is a web content extractor that has a RESTful API and the ability to run pre-store scripts.
Harvest stores the full text of linked articles from RSS feeds or URLs containing links.

--------
![Alt text](doc/emissary4.png?raw=true "ncurses Client")
![Alt text](doc/emissary3.png?raw=true "Feed Groups")
![Alt text](doc/emissary2.png?raw=true "Articles")
<pre>

Installation requires the python interpreter headers, libxml2 and libxslt headers.
Optional article compression requires libsnappy.
All of these can be obtained on debian-based systems with:
sudo apt-get install -y zlib1g-dev libxml2-dev libxslt1-dev python3-dev libsnappy-dev

You're then ready to install the package:
pip install .


 Usage: harvest <args>

  -h, --help            show this help message and exit
  -c, --crontab         Crontab to parse
  --config              (defaults to harvest.config)
  -a, --address         (defaults to 0.0.0.0)
  -p, --port            (defaults to 6362)
  --export              Write the existing database as a crontab
  --key                 SSL key file
  --cert                SSL certificate
  --logfile             (defaults to ./harvest.log)
  --debug               Log to stdout
  --scripts-dir         (defaults to ./scripts/)
  --repl                Start an interactive REPL
  --ncurses             Start the ncurses TUI


Some initial setup has to be done before the system will start.
Communication with Harvest is mainly done over HTTPS connections
and for that you're going to need an SSL certificate and a key:

user@host $ openssl genrsa 4096 > key
user@host $ openssl req -new -x509 -nodes -sha256 -days 365 -key key > cert

To prevent your API keys ever getting put into version control for all
the world to see, you need to put a database URI into the environment:

export HARVEST_DATABASE="sqlite://///home/you/.harvest.db"

Protip: Put that last line in your shells' rc file.

Start an instance in the foreground to obtain your first API key:

user@host $ harvest --cert cert --key key
08/03/2026 16:31:30 - Harvest - INFO - Starting Harvest 3.0.0.
e5a59e0a-b457-45c6-9d30-d983419c43e1
^That UUID is your Primary API key. Add it to this example crontab:

user@host $ cat feeds.txt
apikey: your-api-key-here

# url                                                 name            group            minute  hour    day     month   weekday
http://news.ycombinator.com/rss                       "HN"            "HN"             */15    *       *       *       *
http://phys.org/rss-feed/                             "Phys.org"      "Phys.org"       1       12      *       *       *
http://feeds.nature.com/news/rss/most_recent          "Nature"        "Nature"         30      13      *       *       *

user@host $ harvest -c feeds.txt
Using API key "Primary".
Primary: Processing feed groups.
Primary: HN       "HN"        (*/15 * * * *)
Primary: Phys.org "Phys.org"  (1 12 * * *)
Primary: Nature   "Nature"    (30 13 * * *)

Harvest supports multiple apikey directives in one crontab.
Subsequent feed definitions are associated with the previous key.

Start an instance and connect to it with the REPL:
user@host $ harvest --cert cert --key key &
user@host $ harvest --repl
Harvest 3.0.0
Float64 2026

(3,204) > help

</pre>

If the prospect of creating an NSA profile of your reading habits is
something that rightfully bothers you then my advice is to subscribe
to many things and then use Harvest to read the things that really
interest you.

![Alt text](doc/emissary5.png?raw=true "ncurses programmatic access")
