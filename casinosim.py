import getopt
import math
import multiprocessing
import statistics
import sys
import time

from simulator import betting, simulator, stats, strategy


BETTING_SYSTEMS = {
    "none": betting.NoBetting,
    "martingale": betting.Martingale,
    "idkmartingale": betting.IdkMartingale,
    "fp": betting.FPBetting,
    "fibonacci": betting.Fibonacci,
    "labouchere": betting.Labouchere,
    "simple": betting.SimpleBetting,
    "oscarsgrind": betting.OscarsGrind
}


HELP_GENERAL = [
    (['-h', '--help'], ['print this help']),
    (['-v', '--verbose'], ['print a LOT of extra info']),
    (['-f', '--out-file'], ['output the results to a file']),
]


HELP_SIMULATOR = [
    (['-s', '--strat=FILE'], ['playing strategy file to use (default "strats/strat.txt")']),
    (['-i', '--iterations=ITS'],
     ['how many times to run the simulation until', 'an end condition is reached (default 1)']),
    (['-g', '--gold=GOLD'], ['total gold to start with, or 0 to disable gold',
                             'completely (default 0)']),
    (['    --threads'],
     ['how many processes to run the simulation on (default 0 = auto)']),
    (['    --anti-fallacy'],
     ['enable anti-fallacy strat (after a loss, bet 0 until a win, repeat)'])
]


HELP_BETTING = [
    (['-b', '--bet-system=SYSTEM'], ['betting system to use (default "none")']),
    (['-o', '--bet-options=OPTS'],
     ['comma-separated key=value list of options', 'to pass to the betting system']),
    (['-p', '--positive-prog'], ['use positive progression instead of negative']),
    (['    --list-bet-systems'], ['list available betting systems']),
]


HELP_CONDITIONS = [
    (['-r', '--rounds=ROUNDS'], ['maximum number of rounds to run']),
    (['-t', '--target=GOLD'], ['target gold amount to reach']),
]


def print_help_thing(thing):
    """
    Prints a list of command line options with a description.

    :param thing: list of tuples containing a list of options and a list of description lines
    """
    for (cmds, desc) in thing:
        print("  {:<24}{}".format(", ".join(cmds), desc.pop(0)))
        for line in desc:
            print("  {:<24}{}".format('', line))


def usage(file):
    """
    Prints command help
    """
    print("Usage: {0} [OPTION...]".format(file))

    print("\nGeneral:")
    print_help_thing(HELP_GENERAL)
    print("\nSimulator:")
    print_help_thing(HELP_SIMULATOR)
    print("\nBetting:")
    print_help_thing(HELP_BETTING)
    print("\nEnd conditions:")
    print_help_thing(HELP_CONDITIONS)

    print("\n\nBetting systems:")
    print("  {}".format(", ".join(sorted(BETTING_SYSTEMS.keys()))))


def worker(num, iterations, outq, bjs, rounds, gold):
    total_stats = []
    reasons = []
    for i, _ in enumerate(bjs):
        reasons.append({})
        total_stats.append(stats.BlackjackStats())
        total_stats[i].gold_min = gold[i]
    for _ in range(iterations):
        for i, bj in enumerate(bjs):
            bj.reset()
            (reason, st) = bj.run(rounds)

            total_stats[i].add(st)
            if reason not in reasons:
                reasons[i][reason] = {"count": 0, "gold_end": [], "hands": []}
            reasons[i][reason]["count"] += 1
            reasons[i][reason]["gold_end"].append(st.gold_end)
            reasons[i][reason]["hands"].append(st.total_hands)
    outq.put((reasons, total_stats))


def main():
    if len(sys.argv) < 2:
        usage(sys.argv[0])
        sys.exit(1)

    try:
        opts, _ = getopt.getopt(sys.argv[1:], "hvf:s:i:g:b:o:pr:t:", [
            "help", "verbose", "threads=", "out-file=", "strat=", "iterations=", "gold=", "bet-system=", "bet-options=", "positive-prog", "list-bet-systems", "rounds=", "target=", "anti-fallacy"])
    except getopt.GetoptError as err:
        print(err)
        usage(sys.argv[0])
        sys.exit(2)

    verbose = False
    out_file = None

    def verbose_print(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    def just_print(*args, **kwargs):
        print(*args, **kwargs)
        if out_file is not None:
            kwargs["file"] = out_file
            print(*args, **kwargs)

    # Default options
    iterations = 1
    starting_golds = []
    strat_file = "strats/strat.txt"

    bet_system_names = []
    bet_options = []
    bet_anti_fallacy = False
    bet_positive_prog = False

    # End conditions, at least one should be enabled
    target_gold = []
    rounds = 0

    threads = 0

    for o, a in opts:
        if o in ('-v', '--verbose'):
            verbose = True
        elif o in ('-h', '--help'):
            usage(sys.argv[0])
            sys.exit()
        elif o == '--threads':
            threads = int(a)
        elif o in ('-f', '--out-file'):
            out_file = open(a, mode='w')
        elif o in ('-s', '--strat'):
            strat_file = a
        elif o in ('-b', '--bet-system'):
            bet_system_names.append(a)
        elif o in ('-o', '--bet-options'):
            bet_options.append(a)
        elif o in ('-p', '--positive-prog'):
            bet_positive_prog = True
        elif o == '--list-bet-systems':
            print("Available betting systems:", ", ".join(
                sorted(BETTING_SYSTEMS.keys())))
            sys.exit()
        elif o in ('-i', '--iterations'):
            iterations = int(a)
        elif o in ('-r', '--rounds'):
            rounds = int(a)
        elif o in ('-g', '--gold'):
            starting_golds.append(int(a))
        elif o in ('-t', '--target'):
            target_gold.append(int(a))
        elif o == '--anti-fallacy':
            bet_anti_fallacy = True
        else:
            assert False, "unhandled option"

    if not (len(bet_system_names) == len(starting_golds)):
        just_print('You must have an equal amount of --bet-system and --gold')
        sys.exit(1)

    players = len(bet_system_names)

    if any(x not in BETTING_SYSTEMS for x in bet_system_names) or len(bet_system_names) == 0:
        just_print("Invalid betting system '{}'".format(bet_system_names))
        just_print("Available systems:", ", ".join(
            sorted(BETTING_SYSTEMS.keys())))
        sys.exit(1)

    if len(bet_system_names) > 0 and len(starting_golds) == 0:
        just_print("gold required to use a betting system")
        sys.exit(1)

    if len(target_gold) == 0 and rounds == 0:
        just_print(
            "At least one end condition (--target or --rounds) needs to be enabled.")
        sys.exit(1)

    if threads == 0:
        threads = multiprocessing.cpu_count()

    # we don't need 4 threads to run 1 iteration
    if iterations < threads:
        threads = iterations

    just_print("Casino Simulator 9000!")
    just_print("Using strat file:", strat_file)
    just_print("Using betting system:", bet_system_names)
    just_print("  with options:", bet_options)
    if bet_anti_fallacy:
        just_print("Using anti-fallacy strategy")
    just_print("Players: " + str(players))

    # if len(starting_golds) > 0:
    #     just_print()
    #     just_print("{:.<16}{:.>20,}".format("Starting gold", starting_gold))

    # if target_gold > 0:
    #     just_print("{:.<16}{:.>20,}".format("Gold target", target_gold))

    just_print("{:.<16}{:.>20,}".format("Max rounds", rounds))

    just_print()
    just_print("Running {0} iterations of blackjack using {1} processes...".format(
        iterations, threads))

    # Track stats over all iterations my merging each iteration's
    # own stats instance with this one
    total_stats = []
    for i in range(players):
        total_stats.append(stats.BlackjackStats())
        total_stats[i].gold_start = starting_golds[i]
        total_stats[i].gold_min = starting_golds[i]
        if len(target_gold) >= players:
            total_stats[i].gold_target = target_gold[i]
        else:
            total_stats[i].gold_target = target_gold[0]

    total_reasons = []

    def add_reasons(many_reasons):
        for i, reasons in enumerate(many_reasons):
            total_reasons.append({})
            for reason in reasons.keys():
                if reason not in total_reasons:
                    total_reasons[i][reason] = reasons[reason]
                else:
                    total_reasons[i][reason]["count"] += reasons[reason]["count"]
                    total_reasons[i][reason]["gold_end"].extend(
                        reasons[reason]["gold_end"])
                    total_reasons[i][reason]["hands"].extend(reasons[reason]["hands"])

    out_q = multiprocessing.Queue()
    procs = []
    chunksize = int(math.ceil(iterations / float(threads)))

    bet_systems = [BETTING_SYSTEMS[name].from_options(bet_options[i]) for i, name in enumerate(bet_system_names)]

    strat = strategy.BlackjackStrategy.from_file(strat_file)

    bjs = []

    for i, bet_system in enumerate(bet_systems):
        bj = simulator.BlackjackSimulator(strat, bet_system)
        bj.set_starting_gold(starting_golds[i])
        bj.set_anti_fallacy(bet_anti_fallacy)
        bj.set_positive_prog(bet_positive_prog)
        if len(target_gold) >= players:
            bj.set_target_gold(target_gold[i])
        else:
            bj.set_target_gold(target_gold[0])

        bjs.append(bj)

    start = time.perf_counter()
    for i in range(threads):
        p = multiprocessing.Process(
            target=worker,
            args=(i, chunksize, out_q, bjs, rounds, starting_golds))
        procs.append(p)
        p.start()

    # for _ in range(threads):
    (reasons, st) = out_q.get()
    add_reasons(reasons)
    for i in range(players):
        total_stats[i].add(st[i])

    for p in procs:
        p.join()

    end = time.perf_counter()

    just_print("Completed in {:.2f}s".format(end - start))
    just_print()

    # Display end reasons and stats
    just_print("Results:")
    for i, total_reason in enumerate(total_reasons):
        just_print('\n\nPlayer: ' + str(i + 1))
        just_print('Strat: ' + bet_system_names[i])
        just_print('Starting gold: ' + str(starting_golds[i]))
        just_print('Bet options: ' + str(bet_options[i]))
        if len(target_gold) >= players:
            just_print('Target gold: ' + str(target_gold[i]))
        elif len(target_gold) > 0:
            just_print('Target gold: ' + str(target_gold[0]))
        just_print()
        for rs in sorted(total_reason.keys()):
            s = total_reason[rs]
            just_print("  {:.<22}{:.>12,} ({:>6.2%})".format(
                rs, s["count"], s["count"] / iterations))
            # just_print(s["gold_end"])
            just_print("    {:.<16}{:.>16,.2f}".format(
                "Avg. end gold", statistics.mean(s["gold_end"])))
            just_print("    {:.<16}{:.>16,.2f}".format(
                "Avg. hands dealt", statistics.mean(s["hands"])))
        just_print("\nStats:")
        total_stats[i].print(just_print)
        if out_file is not None:
            out_file.close()

    just_print(total_stats)



if __name__ == "__main__":
    main()
