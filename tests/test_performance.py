
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock
from orchestrator.engine.reasoner import ChainOfThoughtReasoner, ReasoningResult

class MockClient:
    async def complete(self, messages, temperature, max_tokens):
        # Simulate slow model response
        await asyncio.sleep(0.5) 
        return MagicMock(content="<thinking>Step 1</thinking><answer>42</answer>")

async def run_test():
    print("Starting performance test...")
    tools = {}
    reasoner = ChainOfThoughtReasoner(tools)
    client = MockClient()
    
    start_time = time.time()
    
    # Run with self-consistency (3 samples)
    # Each sample takes 0.5s. 
    # Sequential: ~1.5s
    # Parallel: ~0.5s
    await reasoner.reason(
        task="Test task",
        conversation_history=[],
        client=client,
        emit_thinking=lambda x: None,
        run_id="test_run",
        max_iterations=1,
        use_self_consistency=True
    )
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Total duration: {duration:.2f}s")
    
    if duration < 1.0:
        print("PASS: Execution was parallel (took < 1.0s)")
    else:
        print("FAIL: Execution was likely sequential (took >= 1.0s)")

if __name__ == "__main__":
    asyncio.run(run_test())
