import math
import random


class BettingSystem:
    def __init__(self):
        self.starting_gold = 0
        self.end_reason = None

    @staticmethod
    def parse_options(options):
        opts = {}
        for pairs in options.strip().split(','):
            kv = pairs.split('=')
            if len(kv) > 1:
                opts[kv[0]] = kv[1]
            elif len(kv) > 0:
                opts[kv[0]] = True

        return opts

    @staticmethod
    def from_options(options):
        return BettingSystem()

    def can_double(self):
        return True

    def reset(self):
        self.end_reason = None

    def set_starting_gold(self, gold):
        self.starting_gold = gold

    def set_player(self, pl):
        self.player = pl

    def on_win(self, hands):
        pass

    def on_loss(self, hands):
        pass

    def on_tie(self):
        pass

    def get_next_bet(self):
        return 0


class NoBetting(BettingSystem):
    pass


class SimpleBetting(BettingSystem):
    def __init__(self, bet):
        BettingSystem.__init__(self)
        self.bet = bet

    @staticmethod
    def from_options(options):
        opts = BettingSystem.parse_options(options)
        if 'bet' not in opts:
            raise RuntimeError("SimpleBetting requires 'bet' option")
        return SimpleBetting(int(opts["bet"]))

    def get_next_bet(self):
        return self.bet


class Martingale(BettingSystem):
    def __init__(self, starting):
        BettingSystem.__init__(self)

        self.starting_bet = starting
        self.next_bet = starting

    @staticmethod
    def from_options(options):
        opts = BettingSystem.parse_options(options)
        if 'starting-bet' not in opts:
            raise RuntimeError("Martingale requires 'starting-bet' option")
        return Martingale(int(opts["starting-bet"]))

    def reset(self):
        self.next_bet = self.starting_bet

    def on_win(self, hands):
        self.next_bet = self.starting_bet

    # The goal in Martingale is to recoup any losses and profit by the starting bet
    # after a string of losses. We need to count splits and doubledowns as additional wins/losses to
    # bet accurately.
    # For example, a hand is split twice into three hands. One of those loses a doubledown, one ties and one wins.
    # To win back the lost gold, we need to count the +-s from wins/losses: -2 from double loss, 0 from tie and
    # +1 from win, for a total of -1. Values <0 are losses, so `on_loss` is called with `hands=1`.
    def on_loss(self, hands):
        #print("on_loss", hands, self.next_bet)
        self.next_bet *= (1 + hands)

    def on_tie(self):
        pass

    def get_next_bet(self):
        return self.next_bet


class AntiMartingale(BettingSystem):
    def __init__(self, starting):
        BettingSystem.__init__(self)

        self.starting_bet = starting
        self.next_bet = starting

    @staticmethod
    def from_options(options):
        opts = BettingSystem.parse_options(options)
        if 'starting-bet' not in opts:
            raise RuntimeError("AntiMartingale requires 'starting-bet' option")
        return Martingale(int(opts["starting-bet"]))

    def reset(self):
        self.next_bet = self.starting_bet

    def on_win(self, hands):
        self.next_bet *= (1 + hands)

    def on_loss(self, hands):
        self.next_bet = self.starting_bet

    def on_tie(self):
        pass

    def get_next_bet(self):
        return self.next_bet


class IdkMartingale(BettingSystem):
    def __init__(self, starting):
        BettingSystem.__init__(self)

        self.starting_bet = starting
        self.next_bet = starting
        self.last_result = ""

    @staticmethod
    def from_options(options):
        opts = BettingSystem.parse_options(options)
        if 'starting-bet' not in opts:
            raise RuntimeError("IdkMartingale requires 'starting-bet' option")
        return Martingale(int(opts["starting-bet"]))

    def reset(self):
        self.next_bet = self.starting_bet

    def on_win(self, hands):
        if self.last_result == "loss":
            self.next_bet = self.starting_bet
        else:
            self.next_bet *= (1 + hands)
        self.last_result = "win"

    def on_loss(self, hands):
        if self.last_result == "win":
            self.next_bet = self.starting_bet
        else:
            self.next_bet *= (1 + hands)
        self.last_result = "loss"

    def on_tie(self):
        pass

    def get_next_bet(self):
        return self.next_bet


class FPBetting(BettingSystem):
    def __init__(self, stacks, levels, stack_multi, bet_multi):
        BettingSystem.__init__(self)

        self.stacks = stacks
        self.levels = levels

        self.stack_multiplier = stack_multi
        self.bet_multiplier = bet_multi

        temp = 0
        for n in range(self.stacks):
            temp += self.stack_multiplier ** n
        self.total_div = temp
        temp = 0
        for n in range(self.levels):
            temp += self.bet_multiplier ** n
        self.stack_divider = temp

        self.stacks = []

    @staticmethod
    def from_options(options):
        opts = BettingSystem.parse_options(options)
        missing = []
        for o in ['stacks', 'levels', 'stack-multi', 'bet-multi']:
            if o not in opts:
                missing.append(o)
        if len(missing) > 0:
            raise RuntimeError(
                "FP requires options: {}".format(",".join(missing)))
        return FPBetting(int(opts['stacks']), int(opts['levels']), float(opts['stack-multi']), float(opts['bet-multi']))

    def reset(self):
        BettingSystem.reset(self)
        self.stacks = []
        self.first_stack()

    def can_double(self):
        return self.current_stack >= self.next_bet

    def first_stack(self):
        self.current_stack = math.floor(self.player.gold/self.total_div)
        self.stacks.append(self.current_stack)
        self.next_bet = math.floor(self.current_stack/self.stack_divider)

    def next_stack(self):
        old_left = self.current_stack
        prev_stack = self.stacks[-1]
        self.current_stack = math.floor(prev_stack * self.stack_multiplier)
        self.stacks.append(self.current_stack)
        self.next_bet = math.floor(self.current_stack/self.stack_divider)

        if self.current_stack > self.player.gold:
            # print("fuck")
            self.end_reason = "Ran out of gold."
            return

        # print("stack ended, start new stack", self.current_stack)
        # print("", "prev stack", prev_stack)
        # print("", "leftovers", old_left)
        # print("", "new stack with leftovers", self.current_stack + old_left)
        # print("", "total left", self.player.gold)
        self.current_stack += old_left

    def rewind_stack(self):
        # print("rewinding stack", self.current_stack)
        # print("", "total left", self.player.gold)
        over = self.current_stack - self.stacks.pop()
        self.current_stack = 0
        # print("over", over)
        # print("lenstacks", len(self.stacks))
        while len(self.stacks) > 0 and over > self.stacks[-1]:
            full = self.stacks.pop()
            #print("fullstack", full)
            over -= full
            #print("over", over)
        if len(self.stacks) == 0:
            self.first_stack()
        else:
            self.next_stack()

    def on_win(self, hands=1):
        won = self.next_bet * hands
        #print("won", won)
        self.current_stack += won
        #print("stack", self.current_stack)
        if len(self.stacks) > 1 and self.current_stack >= (self.stacks[-1] + self.stacks[-2]):
            #print("won back lost stack")
            self.rewind_stack()
        else:
            self.next_bet = math.floor(self.current_stack/self.stack_divider)

    def on_loss(self, hands=1):
        lost = self.next_bet * hands
        #print("lost", lost)
        self.current_stack -= lost
        #print("stack", self.current_stack)
        self.next_bet = math.floor(lost * self.bet_multiplier)
        if self.current_stack < self.next_bet:
            self.next_stack()

    def on_tie(self):
        pass

    def get_next_bet(self):
        return self.next_bet


def test_thing():
    fpb = FPBetting(5, 8, 2.223, 2.223)
    fpb.set_starting_gold(800000)
    #print("bet", fpb.get_next_bet())
    # for _ in range(40):
    #     if fpb.total_gold < 0:
    #         break
    #     print()
    #     if random.randint(1,5) == 1:
    #         fpb.on_win()
    #     else:
    #         fpb.on_loss()
    #     print("next_bet", fpb.get_next_bet())
    for _ in range(16):
        fpb.on_loss()
    for _ in range(200):
        fpb.on_win()
    # for _ in range(16):
    #    fpb.on_loss()


if __name__ == "__main__":
    test_thing()
