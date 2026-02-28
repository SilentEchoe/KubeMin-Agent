import pytest
from kubemin_agent.agents.game_audit.assert_tool import AssertTool

@pytest.mark.asyncio
async def test_assert_equal():
    tool = AssertTool()
    # Exact match
    res = await tool.execute(assertion_type="assert_equal", expected="100", actual="100")
    assert res.startswith("PASS")
    
    # Mismatch
    res = await tool.execute(assertion_type="assert_equal", expected="100", actual="99")
    assert res.startswith("FAIL")
    
    # Whitespace resilience
    res = await tool.execute(assertion_type="assert_equal", expected=" 100", actual="100 ")
    assert res.startswith("PASS")

@pytest.mark.asyncio
async def test_assert_not_equal():
    tool = AssertTool()
    res = await tool.execute(assertion_type="assert_not_equal", expected="100", actual="99")
    assert res.startswith("PASS")
    
    res = await tool.execute(assertion_type="assert_not_equal", expected="100", actual="100")
    assert res.startswith("FAIL")

@pytest.mark.asyncio
async def test_assert_contains():
    tool = AssertTool()
    res = await tool.execute(assertion_type="assert_contains", expected="success", actual="login success message")
    assert res.startswith("PASS")
    
    res = await tool.execute(assertion_type="assert_contains", expected="error", actual="login success message")
    assert res.startswith("FAIL")

@pytest.mark.asyncio
async def test_assert_delta():
    tool = AssertTool()
    
    # Matching delta (e.g. comparing the difference: new - old == -10)
    res = await tool.execute(assertion_type="assert_delta", expected="-10", actual="-10.0")
    assert res.startswith("PASS")
    
    # Matching delta with floats
    res = await tool.execute(assertion_type="assert_delta", expected="0.5", actual="0.50000001")
    assert res.startswith("PASS")
    
    # Mismatching delta
    res = await tool.execute(assertion_type="assert_delta", expected="-10", actual="-5")
    assert res.startswith("FAIL")
    
    # Invalid numeric input
    res = await tool.execute(assertion_type="assert_delta", expected="-10", actual="abc")
    assert res.startswith("FAIL")
