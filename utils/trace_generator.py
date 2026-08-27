import random
import json
from datetime import datetime, timedelta

def generate_synthetic_trace(num_requests=100, seed=42):
    """
    Fake LLM inference requests generate karta hai.
    Har request mein: arrival_time, token_count, priority hota hai.
    """
    random.seed(seed)
    requests = []
    current_time = datetime.now()

    for i in range(num_requests):
        # Requests random gaps ke saath aati hain (0.1 se 5 seconds)
        gap = random.uniform(0.1, 5.0)
        current_time += timedelta(seconds=gap)

        request = {
            "request_id": f"req_{i+1}",
            "arrival_time": current_time.isoformat(),
            "input_tokens": random.randint(50, 2000),      # prompt size
            "output_tokens": random.randint(50, 1000),     # expected response size
            "priority": random.choice(["low", "medium", "high"]),
        }
        requests.append(request)

    return requests


def save_trace_to_file(requests, filename="sample_trace.json"):
    with open(filename, "w") as f:
        json.dump(requests, f, indent=2)
    print(f"{len(requests)} requests saved to {filename}")


if __name__ == "__main__":
    trace = generate_synthetic_trace(num_requests=100)
    save_trace_to_file(trace)