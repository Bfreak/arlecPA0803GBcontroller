def classify_duration(dur):
    if 2200 <= dur <= 2300:
        return "START - "  # Start
    elif 150 <= dur <= 349:
        return "1"
    elif 600 <= dur <= 900:
        return "0"
    elif 350 <= dur <= 599:
        return " - END"
    else:
        return "?"