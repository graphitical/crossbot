
import datetime
import os
import sqlite3
import statistics
import numpy as np

from collections import defaultdict, namedtuple
from itertools import cycle
from tempfile import NamedTemporaryFile

# don't use matplotlib gui
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import crossbot

from crossbot.parser import date_fmt


def init(client):

    parser = client.parser.subparsers.add_parser('plot', help='plot something')
    parser.set_defaults(
        command   = plot,
        plot_type = 'normalized',
        smooth    = 0.6,
        num_days  = 7,
        scale     = 'linear',
    )

    ptype = parser.add_argument_group('Plot type')\
                    .add_mutually_exclusive_group()

    ptype.add_argument(
        '--times',
        action = 'store_const',
        dest   = 'plot_type',
        const  = 'times',
        help   = 'Plot the raw times.')

    ptype.add_argument(
        '--normalized',
        action  = 'store_const',
        dest    = 'plot_type',
        const   = 'normalized',
        help    = 'Plot smoothed, normalized scores.'
        ' Higher is better. (Default)')

    appearance = parser.add_argument_group('Plot appearance')
    scales = appearance.add_mutually_exclusive_group()

    scales.add_argument(
        '--log',
        action = 'store_const',
        dest   = 'scale',
        const  = 'symlog')
    scales.add_argument(
        '--linear',
        action = 'store_const',
        dest   = 'scale',
        const  = 'linear')

    appearance.add_argument(
        '-s', '--smooth',
        type    = float,
        metavar = 'S',
        help = 'Smoothing factor between 0 and 0.95.'
        ' Default %(default)s.'
        ' Only applies to plot type `normalized`.')

    dates = parser.add_argument_group('Date range')

    dates.add_argument(
        '--start-date',
        type    = crossbot.date,
        metavar = 'START',
        help    = 'Date to start plotting from.')
    dates.add_argument(
        '--end-date',
        type    = crossbot.date,
        metavar = 'END',
        help    = 'Date to end plotting at. Defaults to today.')
    dates.add_argument(
        '-n', '--num-days',
        type    = int,
        metavar = 'N',
        help    = 'Number of days since today to plot.'
        ' Ignored if both start-date and end-date given.'
        ' Default %(default)s.')

    parser.add_argument(
        '-f', '--focus',
        action  = 'append',
        type    = str,
        metavar = 'USER',
        help    = 'Slack name of player to focus the plot on. Can be used multiple times.')


# a nice way to convert db entries into objects
Entry = namedtuple('Entry', ['userid', 'date', 'seconds'])


def fmt_min(sec, pos):
    minutes, seconds = divmod(int(sec), 60)
    return '{}:{:02}'.format(minutes, seconds)


def plot(client, request):
    '''Plot everyone's times in a date range.
    `plot [plot_type] [num_days] [smoothing] [scale] [start date] [end date]`, all arguments optional.
    `plot_type` is either `normalized` (default) or `times` for a non-smoothed plot of actual times.
    `smoothing` is between 0 (no smoothing) and 1 exclusive. .6 default
    You can provide either `num_days` or `start_date` and `end_date`.
    `plot` plots the last 5 days by default.
    The scale can be `log` or `linear` (default).'''

    args = request.args

    start_date = crossbot.date(args.start_date)
    end_date   = crossbot.date(args.end_date)

    start_dt = datetime.datetime.strptime(start_date, date_fmt).date()
    end_dt   = datetime.datetime.strptime(end_date,   date_fmt).date()

    # we only use num_days if the other params weren't given
    # otherwise set num_days based the given range
    if start_date == end_date:
        start_dt -= datetime.timedelta(days=args.num_days)
        start_date = start_dt.strftime(date_fmt)
    else:
        args.num_days = (end_dt - start_dt).days

    dt_range = [start_dt + datetime.timedelta(days=i) for i in range(args.num_days + 1)]
    date_range = [dt.strftime(date_fmt) for dt in dt_range]

    if not 0 <= args.smooth <= 0.95:
        request.reply('smooth should be between 0 and 0.95', direct=True)

    with sqlite3.connect(crossbot.db_path) as con:
        query = '''
        SELECT userid, date, seconds
        FROM {}
        WHERE date
          BETWEEN date(?)
          AND     date(?)
        ORDER BY date, userid'''.format(args.table)

        cur = con.execute(query, (start_date, end_date))
        entries = [Entry._make(tup) for tup in cur]

    if args.plot_type == 'normalized':
        scores_by_user = get_normalized_scores(entries, args)
        ticker = matplotlib.ticker.MultipleLocator(base=0.25)
        formatter = matplotlib.ticker.ScalarFormatter(useOffset=False)
    elif args.plot_type == 'times':
        scores_by_user = get_times(entries, args)
        sec = 30 if args.table == crossbot.tables['mini'] else 60 * 5
        ticker = matplotlib.ticker.MultipleLocator(base=sec)
        formatter = matplotlib.ticker.FuncFormatter(fmt_min) # 1:30
    else:
        raise RuntimeError('invalid plot_type {}'.format(args.plot_type))

    # find contiguous sequences of dates
    user_seqs = defaultdict(list)
    for userid, date_scores in scores_by_user.items():
        date_seq = []

        for date in date_range:
            score = date_scores.get(date)

            if score is not None:
                date_seq.append((date, score))
                continue

            # no score for this date, lets break the sequence, adding this
            # contiguous sequence to user_seqs
            if date_seq:
                user_seqs[userid].append(date_seq)
                date_seq = []

        # get the final sequence if one exists
        if date_seq:
            user_seqs[userid].append(date_seq)

    width, height, dpi = (120*args.num_days), 600, 100
    width = max(400, min(width, 1000))

    fig = plt.figure(figsize=(width/dpi, height/dpi), dpi=dpi)
    ax = fig.add_subplot(1,1,1)

    cmap = plt.get_cmap('nipy_spectral')
    markers = cycle(['-o', '-X', '-s', '-^'])

    n_users = len(user_seqs)
    colors = [cmap(i / n_users) for i in range(n_users)]

    max_score = -100000

    for (userid, date_seqs), color, marker in zip(user_seqs.items(), colors, markers):
        name = client.user(userid)
        label = name

        if args.focus:
            color = color if name in args.focus else '#0F0F0F0F'

        for date_seq in date_seqs:
            dates, scores = zip(*date_seq)
            max_score = max(max_score, max(scores))
            dates = [datetime.datetime.strptime(d, date_fmt).date() for d in dates]

            ax.plot_date(mdates.date2num(dates), scores, marker, label=label, color=color)

            # make sure that we don't but anyone in the legend twice
            label = '_nolegend_'

    ax.set_yscale(args.scale)
    ax.yaxis.set_major_locator(ticker)
    ax.yaxis.set_major_formatter(formatter)

    fig.autofmt_xdate()
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %-d')) # May 3

    # hack to prevent crashes on the regular crosswords
    ax.xaxis.get_major_locator().MAXTICKS = 10000

    ax.legend(fontsize=6, loc='upper left')

    temp = NamedTemporaryFile(suffix='.png', delete=False)
    fig.savefig(temp, format='png', bbox_inches='tight')
    temp.close()
    plt.close(fig)

    request.upload('plot', temp.name)

    # don't renome temp files if using command line client,
    # let the user see them
    if not isinstance(request, crossbot.client.CommandLineRequest):
        os.remove(temp.name)


#########################
### Scoring Functions ###
#########################


# these should all take a list of Entry objects and the args object, and a
# return a dict that looks like this:
# scores[userid][date] = score


def get_normalized_scores(entries, args):
    """Generate smoothed scores based on mean, stdev of that days times. """

    times_by_date = defaultdict(dict)
    for e in entries:
        times_by_date[e.date][e.userid] = e.seconds

    sorted_dates = sorted(times_by_date.keys())

    # failures come with a heaver ranking penalty
    MAX_SCORE = 1.5
    FAILURE_PENALTY = -2

    def mk_score(mean, t, stdev):
        if t < 0:
            return FAILURE_PENALTY
        if stdev == 0:
            return 0

        score = (mean - t) / stdev
        return np.clip(score, -MAX_SCORE, MAX_SCORE)

    # scores are the stdev away from mean of that day
    scores = {}
    for date, user_times in times_by_date.items():
        times = [t for t in user_times.values() if t is not None]
        # make failures 1 minute worse than the worst time
        times = [t if t >= 0 else max(times) + 60 for t in times]
        q1, q3 = np.percentile(times, [25,75])
        stdev  = statistics.pstdev(times)
        o1, o3 = q1 - stdev, q3 + stdev
        times  = [t for t in times if o1 <= t <= o3]
        mean  = statistics.mean(times)
        stdev  = statistics.pstdev(times, mean)
        scores[date] = {
            userid: mk_score(mean, t, stdev)
            for userid, t in user_times.items()
            if t is not None
        }

    new_score_weight = 1 - args.smooth
    running = defaultdict(list)

    weighted_scores = defaultdict(dict)
    for date in sorted_dates:
        for user, score in scores[date].items():

            old_score = running.get(user)

            new_score = score * new_score_weight + old_score * (1 - new_score_weight) \
                        if old_score is not None else score

            weighted_scores[user][date] = running[user] = new_score

    return weighted_scores


def get_times(entries, args):
    """Just get the times, removing any failures."""

    times = defaultdict(dict)
    for e in entries:
        if e.seconds >= 0:
            # don't add failures to the times plot
            times[e.userid][e.date] = e.seconds

    return times
