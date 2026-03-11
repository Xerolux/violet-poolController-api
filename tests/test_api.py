import aiohttp
import pytest
import pytest_asyncio
from aioresponses import aioresponses
from violet_poolcontroller_api.api import VioletPoolAPI, VioletPoolAPIError

@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m

@pytest_asyncio.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        # Pass low retry counts to make error tests faster
        api = VioletPoolAPI(
            host="192.168.1.100",
            session=session,
            username="admin",
            password="password",
            max_retries=1
        )
        yield api

@pytest.mark.asyncio
async def test_get_readings_success(mock_aioresponse, api_client):
    """Test get_readings returns the correct parsed JSON dictionary."""
    url = "http://192.168.1.100/getReadings?ALL"
    mock_data = {"PUMPSTATE": "2", "PH": 7.2}
    mock_aioresponse.get(url, payload=mock_data, status=200)

    result = await api_client.get_readings()

    assert isinstance(result, dict)
    assert result == mock_data

@pytest.mark.asyncio
async def test_set_pump_speed_success(mock_aioresponse, api_client):
    """Test set_pump_speed formats the request correctly and returns success."""
    url = "http://192.168.1.100/setFunctionManually?PUMP%2CON%2C0%2C2"
    mock_aioresponse.get(url, body="OK", status=200)

    result = await api_client.set_pump_speed(speed=2, duration=0)

    assert result["success"] is True
    assert result["response"] == "OK"

@pytest.mark.asyncio
async def test_request_server_error(mock_aioresponse, api_client):
    """Test that a 500 error raises VioletPoolAPIError after retrying."""
    url = "http://192.168.1.100/getReadings?ALL"
    mock_aioresponse.get(url, status=500)
    # the second time it retries
    mock_aioresponse.get(url, status=500)

    with pytest.raises(VioletPoolAPIError) as exc_info:
        await api_client.get_readings()

    assert "Error communicating with Violet controller" in str(exc_info.value)
