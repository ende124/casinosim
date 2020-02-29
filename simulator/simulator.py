import random
import time

from casinobot import blackjack, player
from simulator import betting, stats, strategy


class Phenny:
    """
    Mock of the IRC bot Phenny's interface
    """

    def __init__(self, out):
        self.print = out

    def say(self, msg):
        """
        Send a message to the "channel".
        """
        self.print("Phenny:", msg)
        pass

    def write(self, msg):
        """
        Send a raw(-er) IRC message, e.g. a NOTICE to a specific user.
        """
        self.print("Phenny:", msg)
        pass


class BlackjackHooksList:
    def __init__(self, hooks):
        self.hooks = hooks
        self.output = None

    def print(self, *args):
        if self.output is not None:
            self.output(*args)

    def getHook(self, hook):
        return self.hooks[hook]

    def getList(self):
        return self.hooks

    def setPropOnAll(self, prop, value):
        self.hooks[prop] = value

    def set_positive_prog(self, enable):
        self.setPropOnAll("positive_prog", enable)

    def set_anti_fallacy(self, enable):
        self.setPropOnAll("anti_fallacy", enable)

    def reset_results(self):
        self.setPropOnAll('wins', 0)
        self.setPropOnAll('losses', 0)
        self.setPropOnAll('ties', 0)
        self.setPropOnAll('surrenders', 0)

    def on_init(self, bj):
        self.print("on_init")


class BlackjackHooks:
    """
    Contains callbacks from CasinoBot, to interface with our strategy and
    betting systems.

    Hand results and doubledowns are tracked in order to accurately pick an
    action on multi-hand rounds. E.g. splitting twice to three hands, with one doubledown
    loss (-2), one normal win (+1) and one tie (0) will be handled as one normal loss (-1).
    """

    def __init__(self, players, out=None):
        self.players = players
        self.output = out
        self.anti_fallacy = False
        self.af_trigger = False
        self.positive_prog = False

        self.reset_results()

    def print(self, *args):
        if self.output is not None:
            self.output(*args)

    def set_positive_prog(self, enable):
        self.positive_prog = enable

    def set_anti_fallacy(self, enable):
        """
        Enable or disable anti-fallacy strat. After a loss, it bets zero until a win, then
        continues normal betting until the next loss, rinse and repeat.
        """
        self.anti_fallacy = enable

    def on_init(self, bj):
        """
        Called when the game is initialized.
        """
        self.print("on_init")

    def on_begin_game(self, bj):
        """
        Called when the game starts and bets can be placed.
        """
        self.print("on_begin_game")

        for pl in self.players:
            bet = pl.bet_system.get_next_bet()

            if bet == 0:
                pl.end_reason = "Infinite loop: zero gold bets."
                pl.ended = True

            if self.af_trigger:
                bet = 0

            self.print("Betting:", bet)

            if pl.bet_system.end_reason is not None:
                pl.end_reason = pl.bet_system.end_reason
                pl.ended = True
                return

            if pl.player.gold < bet:
                pl.end_reason = "Ran out of gold."
                pl.ended = True
            else:
                self.print("Phenny:", pl.player.place_bet(bet))

    def reset_results(self):
        """
        Reset hand results.
        """
        for pl in self.players:
            pl.wins = 0
            pl.losses = 0
            pl.ties = 0
            pl.surrenders = 0

    def on_win(self, pl, nat=False):
        """
        Called when a hand is won.
        """
        if pl.did_doubledown:
            self.players[pl.uid - 1].wins += 1
        self.players[pl.uid - 1].wins += 1

    def on_loss(self, pl, surrender=False):
        """
        Called when a hand is lost.
        """
        if pl.did_doubledown:
            self.players[pl.uid - 1].losses += 1
        self.players[pl.uid - 1].losses += 1
        if surrender:
            self.players[pl.uid - 1].surrenders += 1

    def on_tie(self, pl):
        """
        Called when a hand is tied.
        """
        self.players[pl.uid - 1].ties += 1

    def on_start_turn(self, bj, uid):
        """
        Called when a player's turn starts and an action can be made.
        """
        pid = player.players[uid].uid
        self.print("on_start_turn", uid, pid)
        self.choose_action(bj, uid)

    def on_hit(self, bj, uid):
        """
        Called after hitting and an action can be made.
        """
        self.print("on_hit")
        self.choose_action(bj, uid)

    def on_game_over(self, bj):
        """
        Called when the game is over and all cards revealed.
        """
        for pl in self.players:
            res = pl.wins - pl.losses
            if self.positive_prog:
                res = -res
            self.print("res:", res)
            if res < 0:
                pl.bet_system.on_loss(abs(res))
                if self.anti_fallacy:
                    self.af_trigger = True
            elif res > 0 and not self.af_trigger:
                pl.bet_system.on_win(res)
            elif res > 0:
                self.af_trigger = False
            else:
                pl.bet_system.on_tie()
        self.reset_results()

    def choose_action(self, bj, uid):
        """
        Uses the dealer's visible card and own hand to pick an action from
        the selected strategy, and translates different actions to CasinoBot calls.
        """
        if type(uid) is not int:
            return
        self.print("choose_action", uid)
        pl = self.players[uid - 1]
        bet = player.players[uid].bet
        pid = player.players[uid].uid
        hand = player.players[uid].hand
        dealer = player.players[0].hand.cards[1].rank

        st = pl.strat.get_strat(dealer, hand)

        # If we're already at maximum splits (or splitting is not allowed for other reasons),
        # pick a new strategy using the card value total instead of pairs.
        if st == 'P' and (not bj.accept_split or not pl.bet_system.can_double()):
            st = pl.strat.get_strat(dealer, hand, True)

        self.print("Dealer:", bj.show_dealers_hand())
        self.print("Hand:", hand)
        self.print("Strat:", st)
        if st == 'H':
            bj.hit(pid)
        elif st == 'S':
            bj.stand(pid)
        elif st == 'P':
            if pl.gold < bet:
                print("Not enough gold to split")
            if not bj.accept_split:
                raise RuntimeError("Unable to split for some reason")
            bj.split(pid)
        elif st == 'D' or st == 'Dh':
            if bj.accept_doubledown and pl.bet_system.can_double():
                if bet > pl.gold:
                    print("Not enough gold to doubledown")
                bj.doubledown(pid)
            else:
                bj.hit(pid)
        elif st == 'R' or st == 'Rh':
            if bj.accept_surrender:
                bj.surrender(pid)
            else:
                bj.hit(pid)
        elif st == 'Rs':
            if bj.accept_surrender:
                bj.surrender(pid)
            else:
                bj.stand(pid)
        elif st == 'Ds':
            if bj.accept_doubledown and pl.bet_system.can_double():
                bj.doubledown(pid)
            else:
                bj.stand(pid)
        elif st == 'H*':
            if len(hand.cards) > 2:
                bj.stand(pid)
            else:
                bj.hit(pid)
        elif st == '?':
            actions = [bj.stand, bj.hit]
            if bj.accept_doubledown and pl.bet_system.can_double():
                actions.append(bj.doubledown)
            if bj.accept_split and pl.bet_system.can_double():
                actions.append(bj.split)
            if bj.accept_surrender:
                actions.append(bj.surrender)
            random.choice(actions)(pid)
        else:
            raise RuntimeError("missing strategy '{0}'".format(st))


class Player(player.Player):
    name = 'Sim'
    ended = False
    end_reason = 'N/A'

    def __init__(self, strat, bet_system, bet_options, starting_gold,  target_gold, uid):
        self.uid = int(uid)
        player.add_player(self.uid, self.name)
        self.player = player.players[self.uid]
        self.strat = strat
        self.bet_system = bet_system
        self.bet_system.set_player(self.player)
        self.bet_options = bet_options
        self.starting_gold = starting_gold
        self.target_gold = target_gold
        self.gold = starting_gold
        self.stats = stats.BlackjackStats()
        self.player.gold = self.gold

    def reset(self):
        self.stats = stats.BlackjackStats()
        self.gold = self.starting_gold
        self.stats.gold_start = self.starting_gold
        self.stats.gold_max = self.starting_gold
        self.stats.gold_min = self.starting_gold
        # print(players)
        # players.pop(players[players.index(player)])
        if self.uid in player.players:
            player.remove_player(self.uid)
        player.add_player(self.uid, self.name)
        self.player = player.players[self.uid]
        self.player.gold = self.gold
        self.bet_system.reset()
        self.bet_system.set_player(self.player)
        self.bet_system.set_starting_gold(self.starting_gold)
        self.ended = False
        return self

    def __str__(self):
        return 'Player UID: ' + str(self.uid)


class BlackjackSimulator:
    name = 'Sim'

    def __init__(self, pls, out=None):
        self.phenny = Phenny(self.print)
        self.strat = pls[0].strat
        self.output = out

        self.starting_gold = 0
        self.target_gold = 0
        self.rounds = 0
        self.anti_fallacy = False
        self.positive_prog = False

        self.players = pls

        self.reset()

    def reset(self):
        # for p in player.in_game:
        #     player.remove_from_game(p)
        self.hooks = BlackjackHooks(self.players, self.output)
        self.hooks.set_anti_fallacy(self.anti_fallacy)
        self.hooks.set_positive_prog(self.positive_prog)
        self.reset_players()
        self.reset_gold()

    def reset_players(self):
        for pl in self.players:
            pl.reset()
            pl.player.hooks = self.hooks

    def set_positive_prog(self, enable):
        self.positive_prog = enable

    def set_anti_fallacy(self, enable):
        self.anti_fallacy = enable
        self.hooks.set_anti_fallacy(enable)

    def set_starting_gold(self, gold):
        self.starting_gold = gold
        self.reset_gold()

    def reset_gold(self):
        for pl in self.players:
            pl.player.gold = pl.starting_gold
            pl.stats.gold_start = pl.starting_gold
            pl.stats.gold_max = pl.starting_gold
            pl.stats.gold_min = pl.starting_gold

    def set_target_gold(self, target):
        self.target_gold = target

    def print(self, *args):
        if self.output is not None:
            self.output(*args)

    def run(self, rounds):
        end_reason = "N/A"

        curr_round = 0
        runs = 0
        while True:
            runs +=1
            for p in player.in_game:
                player.remove_from_game(p)
            bj = blackjack.Game(self.phenny, 1, self.name, self.hooks)
            for pl in self.players:
                if pl.uid != 1:
                    bj.join(pl.uid)
            bj.begin_game()
            del bj
            curr_round += 1
            for pl in self.players:
                if 0 < rounds <= curr_round:
                    pl.end_reason = "Finished rounds."
                    pl.ended = True
                    continue
                if pl.starting_gold > 0:
                    if pl.player.gold > pl.stats.gold_max:
                        pl.stats.gold_max = pl.player.gold
                    if pl.player.gold < pl.stats.gold_min:
                        pl.stats.gold_min = pl.player.gold
                    if 0 < pl.target_gold <= pl.player.gold:
                        pl.end_reason = 'Reached target gold.'
                        pl.ended = True
            if all(pl.ended for pl in self.players):
                break
        # Update stats

        for pl in self.players:
            pl.stats.gold_end = pl.player.gold

            total = pl.player.wins + pl.player.losses + \
                    pl.player.ties + pl.player.surrenders

            pl.stats.total_hands = total
            pl.stats.wins = pl.player.wins
            pl.stats.losses = pl.player.losses
            pl.stats.ties = pl.player.ties
            pl.stats.surrenders = pl.player.surrenders
            pl.stats.nat_wins = pl.player.nats
            pl.stats.nat_losses = pl.player.natlosses
            pl.stats.win_streak = pl.player.winning_streak_max
            pl.stats.loss_streak = pl.player.losing_streak_max
            pl.stats.tie_streak = pl.player.tie_streak_max
            pl.stats.surrender_streak = pl.player.surrender_streak_max

        return self.players
