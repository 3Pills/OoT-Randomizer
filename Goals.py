validColors = [
    'White',
    'Red',
    'Green',
    'Blue',
    'Light Blue',
    'Pink',
    'Yellow',
    'Black'
]

class Goal(object):

    def __init__(self, world, name, color, items=None, locations=None, lock_locations=None, lock_entrances=None, required_locations=None):
        # early exit if goal initialized incorrectly
        if not items and not locations:
            raise Exception('Invalid goal: no items or destinations set')
        self.world = world
        self.name = name
        if color in validColors:
            self.color = color
        else:
            raise Exception('Invalid goal: Color %r not supported' % color)
        self.items = items
        self.locations = locations
        self.lock_locations = lock_locations
        self.lock_entrances = lock_entrances
        self.required_locations = required_locations or []
        self.weight = 0
        self._item_cache = {}

    def get_item(self, item):
        try:
            return self._item_cache[item]
        except KeyError:
            for i in self.items:
                if i['name'] == item:
                    self._item_cache[item] = i
                    return i
        raise KeyError('No such item %r for goal %r' % (item, self.name))

    def requires(self, item):
        # Prevent direct hints for certain items that can have many duplicates, such as tokens and Triforce Pieces
        return any(i['name'] == item and not i['hintable'] for i in self.items)

class GoalCategory(object):

    def __init__(self, name, priority, goal_count=0, minimum_goals=0, lock_locations=None, lock_entrances=None):
        self.name = name
        self.priority = priority
        self.lock_locations = lock_locations
        self.lock_entrances = lock_entrances
        self.goals = []
        self.goal_count = goal_count
        self.minimum_goals = minimum_goals
        self.weight = 0
        self._goal_cache = {}

    def get_goal(self, goal):
        if isinstance(goal, Goal):
            return goal
        try:
            return self._goal_cache[goal]
        except KeyError:
            for g in self.goals:
                if g.name == goal:
                    self._goal_cache[goal] = g
                    return g
        raise KeyError('No such goal %r' % goal)