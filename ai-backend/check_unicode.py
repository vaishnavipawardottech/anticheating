"""Check unicode characters in chunk text"""
import json

# Read the chunk file
with open("parsing/output/chunks_output_20260217_234042.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

# Check first chunk
text = chunks[0]["text"][:100]  # First 100 chars
print(f"First 100 chars of chunk 0:")
print(repr(text))
print()

# Show unicode codepoints
print("Unicode analysis:")
for i, char in enumerate(text[:50]):
    if char in [' ', '\n', '\t']:
        print(f"  Index {i}: {repr(char)} (U+{ord(char):04X}) - {type(char).__name__}")
