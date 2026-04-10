import random
def recursive_poem(depth):
    if depth < 0:
        return ""
    line = f"Line {depth}: The echo whispers through the silent deep.\n"
    return line + recursive_poem(depth - 1)

print(recursive_poem(5))

