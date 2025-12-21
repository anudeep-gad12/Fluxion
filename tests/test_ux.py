
import asyncio
import time
from unittest.mock import MagicMock, Mock

# Mock client for test
class MockClient:
    async def complete(self, messages, temperature, max_tokens):
        # Simulate delay
        await asyncio.sleep(0.1)
        return MagicMock(content="<thinking>This is a thought.</thinking><answer>42</answer>")

# Import AFTER defining mocks if needed, but here we just test logic flow
from orchestrator.engine.reasoner import ChainOfThoughtReasoner

async def run_test():
    print("Starting UX verification test...")
    tools = {}
    reasoner = ChainOfThoughtReasoner(tools)
    client = MockClient()
    
    # Track emitted thinking
    emitted_msgs = []
    def capture_thinking(msg):
        emitted_msgs.append(msg)
        print(f"UI Received: {msg}")
    
    start_time = time.time()
    
    # Run with self-consistency
    await reasoner.reason(
        task="Test task",
        conversation_history=[],
        client=client,
        emit_thinking=capture_thinking,
        run_id="test_run",
        max_iterations=1,
        use_self_consistency=True
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Total duration: {duration:.2f}s")
    print(f"Emitted messages count: {len(emitted_msgs)}")
    
    if len(emitted_msgs) > 0:
        print("PASS: Thinking was emitted during execution.")
    else:
        print("FAIL: No thinking emitted.")

if __name__ == "__main__":
    asyncio.run(run_test())
