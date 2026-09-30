def process_table(table, limit):
    rows = len(table)
    total = 0
    positive = 0
    negative = 0
    for i in range(rows):
        cols = len(table[i])
        for j in range(cols):
            value = table[i][j]
            if value > 0:
                positive += 1
            elif value < 0:
                negative += 1
            total += value
    rest = abs(total)
    steps = 0
    while rest > limit:
        rest //= 2
        steps += 1
    match steps % 3:
        case 0:
            bonus = 10
        case 1:
            bonus = 5
        case _:
            bonus = 0
    for k in range(steps):
        if k % 2 == 0:
            bonus += k
    if positive > negative:
        result = total + bonus
    else:
        result = total - bonus
    return result
