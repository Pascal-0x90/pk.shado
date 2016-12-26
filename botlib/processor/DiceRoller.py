import collections
import random

import sympy
from pyparsing import Literal, Word, oneOf, Optional, Group, ZeroOrMore


# dice roller!
# can perform several different types of rolls based on the roll tokens

# The first integer is the number of dice to roll
# 3

# Sides, or FATE dN
# The second segment is the number of sides, with the token of dX
# d6
# You can replace the number with a capital F for FATE dice
# dF

# after this N can always represent a number, or a comparator and number.

########################### COUNTERS
# Successes N
# To count successes instead of totals, add a comparator after the
# sides
# >5

# Failures fN
# to count failures, use the fX token with a comparator or just the side
# f1 or f<2

########################### ROLL MODIFIERS
# Exploding Dice xN
# Exploding dice roll an additional die if the maximum, on that die, is
# rolled.
# rolling 5d6x6
# ( 6+5+1+1+1+2 )= 16

# Compounding Dice xxN
# Sometimes, you may want the exploded dice rolls to be added together
# under the same, original roll.
# rolling 5d6xx6
# ( 3+3+5+4+10 )= 25

# Penetrating Dice xpN/xxpN
# Simply put, any exploded dice are recorded as one less
# rolling 5d6xp6
# ( 1+5+3+3+6+0 )= 18

# reroll rN
# If the dice matches, reroll. Defaults to lowest. Reroll until higher.

# reroll once roN
# If the dice matches, reroll. Defaults to lowest. Reroll only once.

########################## RESULT MODIFIERS, NO MODIFIERS APPLIED
# Keep and Drop khN/klN/dhN/dlN



class DiceRoller(object):
    # the dice expression
    dexp = ''
    # an array of results, usually only one indice is needed but for cumulative rolls
    result = []
    # basic dice, or fate dice?
    type = ''

    # Fate set (the faces of fate since they're not the standard sequence)
    fate_set = [-1, 0, 1]

    # methods (grouped by defaults)
    counter_methods = ["s", "f"]
    roll_modifier_methods = ["x", "xx", "xp", "xxp", "r", "ro"]
    pool_modifier_methods = ["k", "kh", "kl", "d", "dh", "dl"]

    high_methods = ["x", "xx", "xp", "xxp", "k", "kh", "dh"]
    low_methods = ["f", "kl", "d", "dl", "r", "ro"]

    # succ of fail
    success = 0
    fail = 0

    all_methods = ' '.join(counter_methods + roll_modifier_methods + pool_modifier_methods)

    def __init__(self, dexp):
        self.dexp = dexp
        self.parse_input(dexp)
        self.roll = self.roll_die(self.parsed_string.number_of_dice, self.parsed_string.sides)
        self.result = self.dropper_keeper(self.roll)

    def parse_input(self, expression):
        # a dice roll is composed of the following
        # the number of dice
        # the number of sides
        # optional formula (for successes)
        # optional number for threshhold
        # optional keyword
        # optional formula
        # optional number
        numbers = "0123456789"
        dice_numbers = numbers + 'F'
        dice = Literal("d")

        methods = self.all_methods
        operators = '< <= > >= = !='
        digits = Word(numbers)
        dice_digits = Word(dice_numbers)

        dice_expr = digits.setResultsName("number_of_dice") \
                    + dice \
                    + dice_digits.setResultsName("sides") \
                    + Optional(oneOf(operators).setResultsName("success_evaluator")) \
                    + Optional(digits.setResultsName("success_threshhold")) \
                    + ZeroOrMore(Group(oneOf(methods).setResultsName('method_name') \
                                       + Optional(oneOf(operators).setResultsName("method_operator")) \
                                       + Optional(digits.setResultsName("method_value"))).setResultsName('methods',
                                                                                                         True))

        try:
            parsed_string = dice_expr.parseString(expression)
        except:
            return False

        if parsed_string.sides != 'F':
            self.methods = self.clean_methods(parsed_string)
        else:
            self.methods = {}

        self.dice_dict = self.create_dice_dict(parsed_string.sides)
        self.parsed_string = parsed_string
        return True

    def clean_methods(self, parsed):
        parsed_methods = parsed.methods
        sides = parsed.sides
        methods = {}

        for value in parsed_methods:
            method_name = value.method_name
            # default value is based on method
            if value.method_value:
                val = value.method_value
            else:
                if (value.method_name in self.high_methods):
                    val = sides
                elif (value.method_name in self.low_methods):
                    val = '1'
                else:
                    val = '0'

            if value.method_name not in list(self.pool_modifier_methods):
                if value.method_operator:
                    if value.method_operator == '=':
                        operator = '=='
                    else:
                        operator = value.method_operator
                else:
                    operator = '=='

            # keep
            if method_name[0] == 'k':
                layer = 'high'
                if len(method_name) > 1:
                    if method_name[1] == 'l':
                        layer = 'low'
                methods['k'] = {'val': val, 'layer': layer}
            # drop
            elif method_name[0] == 'd':
                layer = 'low'
                if len(method_name) > 1:
                    if method_name[1] == 'h':
                        layer = 'high'
                methods['d'] = {'val': val, 'layer': layer}
            # exploding flags
            elif method_name[0] == 'x':
                compound = False
                penetrate = False
                if len(method_name) > 1:
                    if method_name[1] == 'x':
                        compound = True
                    elif method_name[1] == 'p':
                        penetrate = True
                    if len(method_name) > 2:
                        if method_name[2] == 'p':
                            penetrate = True
                methods['x'] = {'operator': operator, 'val': val, 'compound': compound, 'penetrate': penetrate}
            # reroll flags
            elif method_name[0] == 'r':
                once = False
                if len(method_name) > 1:
                    if method_name[1] == 'o':
                        once = True
                methods['r'] = {'operator': operator, 'val': val, 'once': once}
            # default
            else:
                methods[method_name] = {'operator': operator, 'val': val}

        # success
        if parsed.success_threshhold:
            s_thresh = parsed.success_threshhold
        else:
            s_thresh = sides
        if parsed.success_evaluator:
            s_eval = parsed.success_evaluator
        else:
            s_eval = '=='

        methods['s'] = {'operator': s_eval, 'val': s_thresh}
        return methods

    def dropper_keeper(self, roll_result):
        methods = self.methods
        rolls = roll_result
        # first we keep
        if 'k' in methods:
            if methods['k']['layer'] == 'low':
                reverse = False
            else:
                reverse = True
            top_rolls = sorted(rolls, reverse=reverse)[:int(methods['k']['val'])]
            del rolls[:]
            rolls = top_rolls

        # then we drop
        if 'd' in methods:
            for i in range(0, int(methods['d']['val'])):
                if methods['d']['layer'] == 'high':
                    rolls.remove(min(rolls))
                else:
                    rolls.remove(max(rolls))
        return rolls

    # don't forget to label the exploding sides!
    def create_dice_dict(self, sides='0'):
        face = collections.defaultdict(int)
        if sides == 'F':
            for i in self.fate_set:
                face[i] = 0
        else:
            i = 1
            while i <= int(sides):
                face[i] = 0
                i += 1
        return face

    def roll_die(self, number, sides):
        dice = {}
        methods = self.methods
        dice = []
        full_roll = []

        for i in range(0, int(number)):
            roll = self.diceRoller(sides)
            # reroll
            if 'r' in methods:
                if sympy.sympify(str(roll) + methods['r']['operator'] + methods['r']['val']):
                    while sympy.sympify(str(roll) + methods['r']['operator'] + methods['r']['val']):
                        roll = self.diceRoller(sides)
                        if methods['r']['once']:
                            break
            # explode
            if 'x' in methods:
                if sympy.sympify(str(roll) + methods['x']['operator'] + methods['x']['val']):
                    explode = self.roll_die(1, sides)

                    if methods['x']['penetrate']:
                        explode[0] -= 1

                    if methods['x']['compound']:
                        roll += explode[0]
                    else:
                        full_roll.append(roll)
                        full_roll.extend(explode)

            if 's' in methods:
                if sympy.sympify(str(roll) + methods['s']['operator'] + methods['s']['val']):
                    self.success += 1

            if full_roll:
                dice.extend(full_roll)
                del full_roll[:]
                full_roll = []
            else:
                dice.extend([roll])

        return dice

    def diceRoller(self, sides):
        if sides == 'F':
            roll = int(random.randint(-1, 1))
        else:
            roll = int(random.randint(1, int(sides)))
        return roll

    def get_die_result(self):
        if not self.result:
            return False
        else:
            roll = self.dice_dict
            data = self.result
            for i in data:
                roll[i] += 1
            sides_final = dict(roll)
            return dict(sides_final)

    def get_roll_result(self):
        if not self.result:
            return False
        else:
            return self.result

    def get_roll_total(self):
        if not self.result:
            return False
        else:
            data = self.result
            return sum(int(i) for i in data)

    def get_count(self, type):
        if not self.result:
            return False
        else:
            data = self.result
            counter = 0
            methods = self.methods
            if type in self.methods:
                for i in data:
                    if sympy.sympify(str(i) + methods[type]['operator'] + methods[type]['val']):
                        counter += 1
        return counter

    def get_fail_count(self):
        return self.get_count('f')

    def get_success_count(self):
        return self.get_count('s')

    def get_sr5_glitch(self):
        if(self.get_fail_count() > (len(self.result)/2)+1):
            return True
        else:
            return False

    def get_result(self):
        rep = ''
        rep += self.dexp + ' '
        rep += str(self.result) + ' '
        rep += 't:' + str(self.get_roll_total()) + ' '
        rep += 'f:' + str(self.get_fail_count()) + ' '
        rep += 's:' + str(self.get_success_count()) + ' '
        return rep

    def get_debug_parse(self):
        return self.parsed_string

    def get_debug_methods(self):
        return self.methods
