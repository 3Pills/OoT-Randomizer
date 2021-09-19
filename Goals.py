from collections import OrderedDict
import logging

from HintList import goalTable, getHintGroup
from Search import Search


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

    def __init__(self, world, name, hint_text, color, items=None, locations=None, lock_locations=None, lock_entrances=None, required_locations=None, create_empty=False):
        # early exit if goal initialized incorrectly
        if not items and not locations and not create_empty:
            raise Exception('Invalid goal: no items or destinations set')
        self.world = world
        self.name = name
        self.hint_text = hint_text
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
        self.category = None
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


    def add_goal(self, goal):
        goal.category = self
        self.goals.append(goal)


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


    def is_beaten(self, search):
        # if the category requirements are already satisfied by starting items (such as Links Pocket),
        # do not generate hints for other goals in the category
        starting_goals = search.can_beat_goals({ self.name: self }, scan_for_items=False)
        return all(map(lambda s: len(starting_goals[self.name]['stateReverse'][s.world.id]) >= self.minimum_goals, search.state_list))


    def update_reachable_goals(self, starting_search, full_search):
        # Only reduce goal item quantity if minimum goal requirements are reachable, 
        # but not the full goal quantity. Primary use is to identify reachable
        # skull tokens, triforce pieces, and plentiful item duplicates with
        # All Locations Reachable off. Beatable check is required to prevent
        # inadvertently setting goal requirements to 0 or some quantity less
        # than the minimum
        # Relies on consistent list order to reference between current state
        # and the copied search
        # IMPORTANT: This is not meant to be called per-world. It is supposed to
        # be called once for all world states for each category type.

        for index, state in enumerate(starting_search.state_list):
            for goal in state.world.goal_categories[self.name].goals:
                if (goal.items is not None):
                    if all(map(full_search.state_list[index].has_item_goal, goal.items)):
                        for i in goal.items:
                            i['quantity'] = min(full_search.state_list[index].item_count(i['name']), i['quantity'])


def replace_goal_names(worlds):
    for world in worlds:
        bosses = [location for location in world.get_filled_locations() if location.item.type == 'DungeonReward']
        for cat_name, category in world.goal_categories.items():
            for goal in category.goals:
                if isinstance(goal.hint_text, dict):
                    for boss in bosses:
                        if boss.item.name == goal.hint_text['replace']:
                            flavorText, clearText, color = goalTable[boss.name]
                            if world.settings.clearer_hints:
                                goal.hint_text = clearText
                            else:
                                goal.hint_text = flavorText
                            goal.color = color
                            break


def update_goal_items(spoiler):
    worlds = spoiler.worlds

    # get list of all of the progressive items that can appear in hints
    # all_locations: all progressive items. have to collect from these
    # item_locations: only the ones that should appear as "required"/WotH
    all_locations = [location for world in worlds for location in world.get_filled_locations()]
    # Set to test inclusion against
    item_locations = {location for location in all_locations if location.item.majoritem and not location.locked and location.item.name != 'Triforce Piece'}

    required_locations = {}
    priority_locations = {}
    always_locations = [location.name for world in worlds for location in getHintGroup('always', world)]
    if spoiler.playthrough:
        # Skip even the checks
        _maybe_set_light_arrows = lambda _: None
    else:
        _maybe_set_light_arrows = maybe_set_light_arrows

    # References first world for goal categories only
    # Goals are changed for beatable-only accessibility per-world
    for cat_name, category in worlds[0].locked_goal_categories.items():

        search = Search([world.state for world in worlds])
        search.collect_pseudo_starting_items()

        category_locks = lock_category_entrances(category, search.state_list)

        if category.is_beaten(search):
            unlock_category_entrances(category_locks, search.state_list)
            continue

        full_search = search.copy()
        full_search.collect_locations()
        reachable_goals = {}
        category.update_reachable_goals(search, full_search)
        reachable_goals = full_search.can_beat_goals({ cat_name: category }, scan_for_items=False)
        identified_locations = search_goals({ cat_name: category }, reachable_goals, search, priority_locations, all_locations, item_locations, always_locations, _maybe_set_light_arrows)
        required_locations.update(identified_locations)

        unlock_category_entrances(category_locks, search.state_list)

    search = Search([world.state for world in worlds])
    search.collect_pseudo_starting_items()
    full_search = search.copy()
    full_search.collect_locations()
    reachable_goals = {}
    for cat_name, category in worlds[0].unlocked_goal_categories.items():
        category.update_reachable_goals(search, full_search)
    reachable_goals = full_search.can_beat_goals(worlds[0].unlocked_goal_categories, scan_for_items=False)
    identified_locations = search_goals(worlds[0].unlocked_goal_categories, reachable_goals, search, priority_locations, all_locations, item_locations, always_locations, _maybe_set_light_arrows, search_woth=True)
    required_locations.update(identified_locations)
    woth_locations = list(required_locations['way of the hero'])
    del required_locations['way of the hero']
    
    # Update WOTH items
    woth_locations_dict = {}
    for world in worlds:
        woth_locations_dict[world.id] = list(filter(lambda location: location.world.id == world.id, woth_locations))
    spoiler.required_locations = woth_locations_dict

    # Fallback to way of the hero required items list if all goals/goal categories already satisfied.
    # Do not use if the default woth-like goal was already added for open bridge/open ganon.
    # If the woth list is also empty, fails gracefully to the next hint type for the distro in either case.
    required_locations_dict = {}
    if not required_locations and 'ganon' not in worlds[0].goal_categories and worlds[0].hint_dist_user['use_default_goals']:
        for world in worlds:
            required_locations_dict[world.id] = {}
            required_locations_dict[world.id]['ganon'] = {}
            locations = [(location, 1, 1) for location in spoiler.required_locations[world.id]]
            c = GoalCategory('ganon', 30, goal_count=1, minimum_goals=1)
            g = Goal(world, 'the hero', 'of the hero', 'White', items=[{'name': 'Triforce','quantity': 1,'minimum': 1,'hintable': True}])
            g.required_locations = locations
            c.add_goal(g)
            world.goal_categories[c.name] = c
            # The real protagonist of the story
            required_locations_dict[world.id]['ganon']['the hero'] = locations
    else:
        # Filter the required location to only include locations in the world
        for world in worlds:
            for cat_name, category in world.goal_categories.items():
                if cat_name in required_locations:
                    for goal in category.goals:
                        if goal.name in required_locations[category.name]:
                            locations = list(filter(lambda location: location[0].world.id == world.id, required_locations[category.name][goal.name]))
                            goal.required_locations = locations
                            if locations:
                                for location in locations:
                                    for goal_world in location[3]:
                                        if goal_world not in required_locations_dict:
                                            required_locations_dict[goal_world] = {}
                                        if category.name not in required_locations_dict[goal_world]:
                                            required_locations_dict[goal_world][category.name] = {}
                                        if goal.name not in required_locations_dict[goal_world][category.name]:
                                            required_locations_dict[goal_world][category.name][goal.name] = {}
                                        if world.id not in required_locations_dict[goal_world][category.name][goal.name]:
                                            required_locations_dict[goal_world][category.name][goal.name][world.id] = []
                                        required_locations_dict[goal_world][category.name][goal.name][world.id].append(location[0])
    spoiler.goal_locations = required_locations_dict
    # Copy of goal categories for the spoiler log to reference
    # since the hint algorithm mutates the world copy
    for world in worlds:
        spoiler.goal_categories[world.id] = OrderedDict(sorted(world.goal_categories.items(), key=lambda kv: kv[1].priority))


def lock_category_entrances(category, state_list):
    # Disable access rules for specified entrances
    category_locks = {}
    if category.lock_entrances is not None:
        for index, state in enumerate(state_list):
            category_locks[index] = {}
            for lock in category.lock_entrances:
                exit = state.world.get_entrance(lock)
                category_locks[index][exit.name] = exit.access_rule
                exit.access_rule = lambda state, **kwargs: False
    return category_locks


def unlock_category_entrances(category_locks, state_list):
    # Restore access rules
    for state_id, exits in category_locks.items():
        for exit_name, access_rule in exits.items():
            exit = state_list[state_id].world.get_entrance(exit_name)
            exit.access_rule = access_rule


def search_goals(categories, reachable_goals, search, priority_locations, all_locations, item_locations, always_locations, _maybe_set_light_arrows, search_woth=False):
    required_locations = {}
    world_ids = [state.world.id for state in search.state_list]
    if search_woth:
        required_locations['way of the hero'] = []
    for location in search.iter_reachable_locations(all_locations):
        # Try to remove items one at a time and see if the goal is still reachable
        if location in item_locations:
            old_item = location.item
            location.item = None
            # copies state! This is very important as we're in the middle of a search
            # already, but beneficially, has search it can start from
            valid_goals = search.can_beat_goals(categories, scan_for_items=True)
            for cat_name, category in categories.items():
                # Exit early if no goals are beatable with category locks
                if reachable_goals[category.name]:
                    if category.name not in required_locations:
                        required_locations[category.name] = {}
                    for goal in category.goals:
                        if ((category.name in valid_goals
                                    and goal.name in valid_goals[category.name])
                            and goal.name in reachable_goals[category.name]
                            and (location.name not in priority_locations
                                    or priority_locations[location.name] == category.name)
                            and not goal.requires(old_item.name)):
                            invalid_states = set(world_ids) - set(valid_goals[category.name][goal.name])
                            hintable_states = list(invalid_states & set(reachable_goals[category.name][goal.name]))
                            if hintable_states:
                                if goal.name not in required_locations[category.name]:
                                    required_locations[category.name][goal.name] = []
                                # Placeholder weights to be set for future bottleneck targeting.
                                # 0 weights for always-hinted locations isn't relevant currently
                                # but is intended to screen out contributions to the overall 
                                # goal/category weights
                                if location.name in always_locations or location.name in location.world.hint_exclusions:
                                    location_weights = (location, 0, 0, hintable_states)
                                else:
                                    location_weights = (location, 1, 1, hintable_states)
                                required_locations[category.name][goal.name].append(location_weights)
                                goal.weight = 1
                                category.weight = 1
                                # Locations added to goal exclusion for future categories
                                # Main use is to split goals between before/after rainbow bridge
                                # Requires goal categories to be sorted by priority!
                                priority_locations[location.name] = category.name
            if search_woth and not valid_goals['way of the hero']:
                required_locations['way of the hero'].append(location)
            location.item = old_item
            _maybe_set_light_arrows(location)
        search.state_list[location.item.world.id].collect(location.item)
    return required_locations


def maybe_set_light_arrows(location):
    if not location.item.world.light_arrow_location and location.item and location.item.name == 'Light Arrows':
        location.item.world.light_arrow_location = location
        logging.getLogger('').debug(f'Light Arrows [{location.item.world.id}] set to [{location.name}]')