from rapidfuzz import process, fuzz
text = "quem e voce"
kb_keys = ["quem é você", "qual seu nome", "o que você faz"]
match_result = process.extractOne(text, kb_keys, scorer=fuzz.WRatio)
print(f"Match result: {match_result}")
