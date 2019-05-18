import random

from collections import defaultdict, Counter


def generate_pairs(users):
    free_users = [u for u in users]
    random.shuffle(free_users)
    user_to_matches = defaultdict(list)
    for i in range(0, len(free_users)-1, 2):
        user_to_matches[free_users[i]] = [free_users[i + 1]]
        user_to_matches[free_users[i + 1]] = [free_users[i]]
    if len(free_users) % 2 == 1:
        user_to_matches[free_users[0]].append(free_users[-1])
        user_to_matches[free_users[-1]].append(free_users[0])
    return user_to_matches


def evaluate_pairs(matching, repeatedness):
    loss = 0
    for u1, peers in matching.items():
        for u2 in peers:
            loss += repeatedness[(u1, u2)]
    return loss


def generate_good_pairs(database, decay=0.5):
    free_users = [str(user['tg_id']) for user in database.mongo_users.find({'wants_next_coffee': True})]
    prev_coffee_pairs = [c['matches'] for c in database.mongo_coffee_pairs.find({})]
    repeatedness = Counter()
    for t, matching in enumerate(prev_coffee_pairs[::-1]):
        for u1, peers in matching.items():
            for u2 in peers:
                repeatedness[(u1, u2)] += decay ** t
    best_score = 100500
    best_pair = None
    for i in range(100):
        matching = generate_pairs(free_users)
        score = evaluate_pairs(matching, repeatedness)
        if score < best_score:
            best_score = score
            best_pair = matching
    return best_pair
