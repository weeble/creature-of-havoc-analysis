import random
from collections import deque, Counter
import copy

def roll(dice):
    if dice.startswith('d'):
        dice = '1' + dice
    count, size = [int(s) for s in dice.split('d')]
    return sum(random.randint(1,size) for i in range(count))

class Stat(object):
    def __init__(self, value, valuemax=None):
        self.value = value
        self.valuemax = valuemax if valuemax is not None else value
    def reset(self):
        self.value = self.valuemax
    def add(self, amount):
        self.value += amount
        self.trim()
    def trim(self):
        if self.value > self.valuemax:
            self.value = self.valuemax
        if self.value < 0:
            self.value = 0
    def add_max(self, amount):
        self.valuemax += amount
        self.trim()
    def __str__(self):
        return '<{}/{}>'.format(self.value, self.valuemax)

class Character(object):
    def __init__(self, name, skill, stamina, luck=0, superpowered=False, manic=False, resilient=False):
        self.name = name
        self.skill = Stat(skill)
        self.stamina = Stat(stamina)
        self.luck = Stat(luck)
        self.attack_bonus = 0
        self.superpowered = superpowered
        self.resilient = resilient
        self.manic = manic
    def test_skill(self):
        skillful = roll('2d6') <= self.skill.value
        return skillful
    def test_luck(self):
        lucky = roll('2d6') <= self.luck.value
        self.luck.add(-1)
        return lucky
    def attack_roll(self):
        result = self.skill.value + roll('2d6') + self.attack_bonus
        if self.manic:
            self.attack_bonus = 0
        return result
    def hero_roll(self):
        a = roll('d6')
        b = roll('d6')
        instant_death = self.superpowered and a == b
        return instant_death, self.skill.value + roll('2d6') + self.attack_bonus
    def kill(self):
        self.stamina.value = 0
    def hurt(self, amount):
        self.stamina.add(-amount)
        if self.manic:
            self.attack_bonus = 2
    def alive(self):
        return self.stamina.value > 0
    def __str__(self):
        return format(self)
    def __format__(self, spec):
        if spec == 't':
            return '<{}, skill={}, stamina={}>'.format(self.name, self.skill.valuemax, self.stamina.valuemax)
        return '<{}, skill={}, stamina={}, luck={})'.format(
                self.name,
                self.skill,
                self.stamina,
                self.luck)

class Combat(object):
    def __init__(self, hero, enemies, aggressive_luck=False):
        self.hero = hero
        self.enemies = list(enemies)
        self.rounds = 0
        self.log = []
        self.aggressive_luck = aggressive_luck
    def do_round(self):
        if self.won():
            return
        self.rounds += 1
        instant_death, hero_roll = self.hero.hero_roll()
        enemy_rolls = [e.attack_roll() for e in self.enemies]
        if instant_death and not self.enemies[0].resilient:
            enemy_rolls[0] = -1
            self.enemies[0].kill()
            self.log.append('instant-death')
        for i, (r, e) in enumerate(zip(enemy_rolls, self.enemies)):
            if r > hero_roll:
                if self.hero.stamina.value == 1 and self.hero.test_luck():
                    self.log.append('lucky-escape')
                else:
                    self.hero.hurt(1)
                    self.log.append('hero-hurt')
        if hero_roll > enemy_rolls[0]:
            if self.aggressive_luck and 3<=self.enemies[0].stamina.value<=4:
                if self.hero.test_luck():
                    self.log.append('lucky-blow')
                    self.enemies[0].hurt(4)
                else:
                    self.log.append('unlucky-blow')
                    self.enemies[0].hurt(1)
            else:
                self.enemies[0].hurt(2)
            self.log.append('enemy-hurt')
        if not self.enemies[0].alive():
            self.enemies = self.enemies[1:]
            self.log.append('enemy-dies')
    def won(self):
        return not self.enemies
    def lost(self):
        return not self.hero.alive()
    def autofight(self):
        while self.hero.alive() and self.enemies:
            self.do_round()
    def __str__(self):
        result = 'won' if self.won() else 'lost' if self.lost() else 'ongoing'
        return '{} after {} rounds. {}'.format(result, self.rounds, self.log)

# DSL

class Seq:
    def __init__(self, *steps):
        self.steps = steps
    def run(self, context):
        context.dofirst(self.steps)

class Fight:
    def __init__(self, enemies, aggressive_luck=False):
        self.enemies = enemies
    def format_enemies(self):
        return ', '.join(format(e,'t') for e in self.enemies)
    def run(self, context):
        enemies = copy.deepcopy(self.enemies)
        combat = Combat(context.hero, enemies)
        combat.autofight()
        if combat.won():
            context.log('Defeated {}'.format(self.format_enemies()))
            context.logstatus()
        else:
            context.die('Killed by {}'.format(self.format_enemies()))
        context.lastcombat = combat

class AddStat:
    def __init__(self, statname, amount, description=None):
        self.statname = statname
        self.amount = amount
        self.description = description
    def run(self, context):
        context.log('{:+} to {}'.format(self.amount, self.statname))
        getattr(context.hero, self.statname).add(self.amount)
        context.logstatus()
        if context.hero.stamina.value <= 0:
            context.die(self.description)

class RestoreStat:
    def __init__(self, statname):
        self.statname = statname
    def run(self, context):
        context.log('Restored {}'.format(self.statname))
        context.logstatus()
        getattr(context.hero, self.statname).reset()

class TestStat:
    def __init__(self, statname, on_pass=None, on_fail=None):
        self.statname = statname
        self.on_pass = on_pass
        self.on_fail = on_fail
    def run(self, context):
        hero = context.hero
        test = {'skill':hero.test_skill, 'luck':hero.test_luck}[self.statname]
        if test():
            context.log('Passed a test of {}'.format(self.statname))
            if self.on_pass is not None:
                context.dofirst([self.on_pass])
        else:
            context.log('Failed a test of {}'.format(self.statname))
            if self.on_fail is not None:
                context.dofirst([self.on_fail])

class Goto:
    def __init__(self, reference):
        self.reference = reference
    def run(self, context):
        context.log('Turning to {}'.format(self.reference))
        context.goto(self.reference)

class Compare:
    comparisons = {
        '<': lambda x,y: x < y,
        '>': lambda x,y: x > y,
        '<=': lambda x,y: x <= y,
        '>=': lambda x,y: x >= y,
        '==': lambda x,y: x == y,
        '!=': lambda x,y: x != y,
    }
    def __init__(self, first, comparison, second, then=None, otherwise=None):
        self.first = first
        self.comparison = comparison
        self.second = second
        self.then = then
        self.otherwise = otherwise
    def evaluate(self, name, context):
        if isinstance(name, int):
            return name
        if name == 'combat-duration':
            return context.lastcombat.rounds
        return roll(name)
    def run(self, context):
        firstv = self.evaluate(self.first, context)
        secondv = self.evaluate(self.second, context)
        ispass = self.comparisons[self.comparison](firstv, secondv)
        if ispass:
            if self.then is not None:
                context.dofirst([self.then])
        else:
            if self.otherwise is not None:
                context.dofirst([self.otherwise])

class Win:
    def run(self, context):
        context.win('You win!')

class Die:
    def __init__(self, message=None):
        self.message = message or 'You died!'
    def run(self, context):
        context.die(self.message)


class Context:
    def __init__(self, hero, references, start, verbose):
        self.hero = hero
        self.references = references
        self.lastcombat = None
        self.won = False
        self.lost = False
        self.goto(start)
        self.verbose = verbose
        self.outcome = None
    def log(self, message):
        if self.verbose:
            print(message)
    def logstatus(self):
        self.log('Your status: {}'.format(self.hero))
    def step(self):
        action = self.stack.pop()
        action.run(self)
    def goto(self, reference):
        self.stack = deque([self.references[reference]])
    def dofirst(self, actions):
        self.stack.extend(reversed(actions))
    def win(self, description=None):
        description = description or 'You won.'
        self.log(description)
        self.outcome = description
        self.won = True
        self.stack = deque()
    def die(self, description=None):
        description = description or 'You died.'
        self.log(description)
        self.outcome = description
        self.lost = False
        self.stack = deque()
    def run(self):
        while self.stack:
            self.step()

book = {
    '1':Seq(
        Compare('1d6', '<=', 3, then=Goto('205')),
        Compare('1d6', '<=', 2, then=Goto('205')),
        Compare('1d6', '<=', 1, then=Goto('205')),
        Fight([Character('CLAWBEAST', 9, 14)]),
        Compare('1d6', '<=', 4, then=AddStat('stamina', 2)),
        Compare('1d6', '<=', 3, then=Die('You were killed by dark elves.')),
        Goto('205'),
    ),
    '205':Seq(
        Fight([Character('HOBBIT', 5, 6)], aggressive_luck=True),
        Compare('combat-duration', '<=', 3,
            then=TestStat('luck', on_fail=Die('You were mind-controlled by a wizard.')),
            otherwise=Compare('1d6', '<=', 4, then=Die('You were mind-controlled by a wizard.'))
        ),
        AddStat('stamina', -2, 'A knight stabbed you in the back.'),
        Fight([Character('ARMOURED KNIGHT', 8, 9)]),
        RestoreStat('stamina'),
        Compare('1d6', '<=', 2, then=AddStat('skill', -1)),
        Compare('1d6', '>=', 4, then=AddStat('stamina', -2)),
        Fight([
            Character('First FLESH-FEEDER', 6, 6),
            Character('Third FLESH-FEEDER', 6, 6),
            Character('Second FLESH-FEEDER', 6, 7),
        ]),
        AddStat('luck', 2),
        Fight([Character('STRONGARM', 7, 8)]),
        Fight([
            Character('THIEF', 8, 6),
            Character('WARRIOR', 7, 7),
        ]),
        AddStat('luck', 1),
        TestStat('luck', on_fail=Die('You drowned in the Bilgewater.')),
        Fight([Character('WARRIOR', 8, 9)]),
        Fight([Character('FIGHTER IN LEATHER ARMOUR', 7, 8)]),
        AddStat('luck', 1),
        Fight([
            Character('First BLOOD ORC', 7, 7),
            Character('Second BLOOD ORC', 8, 7),
        ]),
        AddStat('luck', 2),
        TestStat('luck', on_fail=Die('You drowned in the Bilgewater.')),
        AddStat('stamina', -1, 'You beat yourself against a door.'),
        Fight([
            Character('MANIC BEAST', 7, 8, manic=True),
        ]),
        AddStat('stamina', 4),
        RestoreStat('stamina'),
        AddStat('stamina', 8),
        AddStat('luck', 2),
        RestoreStat('skill'), # There's only one way to lose skill in this path, so we don't bother to track the details.
        Fight([Character('VILLAGER', 7, 8)]),
        AddStat('luck', 2),
        AddStat('stamina', 4),
        Fight([Character('TOADMAN', 9, 9)]),
        RestoreStat('luck'),
        RestoreStat('luck'),
        RestoreStat('stamina'),
        TestStat('skill', on_fail=Die('You could not control the ophidiotaur.')),
        Fight([
            Character('Second BRIGAND', 8, 7),
            Character('First BRIGAND', 8, 9),
        ]),
        TestStat('luck', on_fail=TestStat('luck', on_fail=Die('You were eaten by the Galleykeep crew.'))),
        Fight([
            Character('Second GOBLIN', 5, 5),
            Character('First GOBLIN', 6, 5),
        ]),
        Win()
    ),
} 

def trial(verbose):
    hero = Character('YOU', skill=6 + roll('d6'), stamina=12+roll('2d6'), luck=6+roll('d6'))
    context = Context(hero, book, '1', verbose)
    context.logstatus()
    context.run()
    return context

def main():
    outcomes = Counter()
    victories = 0
    for i in range(10000):
        context = trial(verbose=False)
        outcomes[context.outcome] += 1
        if context.won:
            victories += 1
    for outcome, count in outcomes.most_common():
        print('{:60} {:>6}'.format(outcome, count))
    print('{}% success'.format(victories/100))
    #trial(verbose=True)
    #for trial in range(10000):
    #    hero = Character(skill=6 + roll('d6'), stamina=12+roll('2d6'), luck=6+roll('d6'))
    #    hero.superpowered = True
    #    #enemies = [
    #    #    Character(skill=6, stamina=6),
    #    #    Character(skill=5, stamina=6),
    #    #    Character(skill=6, stamina=7),
    #    #]
    #    #enemies = [ Character(skill=7, stamina=8, manic=True) ]
    #    enemies = [
    #        Character(skill=8, stamina=6),
    # ##       Character(skill=7, stamina=7),
    # #   ]
    # #   combat = Combat(hero, enemies)
    #    combat.autofight()
    #    #print(combat)
    #    #print(hero)
    #    wounds.append(hero.stamina.valuemax - hero.stamina.value)
    #print(sum(wounds) / len(wounds))


    

if __name__ == '__main__':
    main()
