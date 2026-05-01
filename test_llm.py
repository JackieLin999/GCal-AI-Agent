from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import torch

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",          # best quality 4-bit format
    bnb_4bit_compute_dtype=torch.float16, # compute in fp16 for speed
    bnb_4bit_use_double_quant=True,      # extra compression, minimal quality loss
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto"                    # automatically puts model on GPU
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print(f"🖥️  Device: {next(model.parameters()).device}")

def ask(prompt, system="You are a helpful assistant."):
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]
    # format messages the way this model expects
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.7,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id
        )
    
    # strip the input tokens, only return new generated tokens
    generated = outputs[0][inputs.input_ids.shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True)

# --- Test 1: basic response ---
print("\n🧪 Test 1: Basic response")
print(ask("What is 2 + 2? Answer in one sentence."))

# --- Test 2: JSON output (critical for your agent) ---
print("\n🧪 Test 2: JSON output")
response = ask("""
Return a JSON object with two fields:
- name: your name
- capability: what you can do

Return only valid JSON, nothing else.
""")
print(response)

# --- Test 3: scheduling reasoning ---
print("\n🧪 Test 3: Scheduling reasoning")
response = ask("""
I have these free time blocks on Tuesday:
- 9:00 AM - 10:00 AM
- 2:00 PM - 5:00 PM

I need to study for an exam on Wednesday.
Suggest how to fill these blocks. Return as JSON list:
[{"title": "...", "start": "HH:MM", "end": "HH:MM"}]

Return only valid JSON, nothing else.
""")
print(response)