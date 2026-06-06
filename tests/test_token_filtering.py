import pytest
from django.utils import timezone
from router.models import Server, Model
from router.repositories.servers import ServerRepository
from router.services.parser import RequestParser

@pytest.mark.django_db
def test_server_filtering_by_context_window():
    # Setup
    model = Model.objects.create(model_name="test-model", concurrent_limit=10)
    
    # Large context server
    s_large = Server.objects.create(
        model_id=model.id,
        base_url="http://large.example",
        is_online=True,
        context_window=100000
    )
    
    # Small context server
    s_small = Server.objects.create(
        model_id=model.id,
        base_url="http://small.example",
        is_online=True,
        context_window=1000
    )
    
    # Case 1: Small request - should return both
    servers = ServerRepository.list_by_model_id(model.id, estimate_tokens=500)
    assert len(servers) == 2
    assert s_large in servers
    assert s_small in servers
    
    # Case 2: Large request - should only return large server
    servers = ServerRepository.list_by_model_id(model.id, estimate_tokens=50000)
    assert len(servers) == 1
    assert s_large in servers
    assert s_small not in servers
    
    # Case 3: Very large request - should return none
    servers = ServerRepository.list_by_model_id(model.id, estimate_tokens=200000)
    assert len(servers) == 0

@pytest.mark.django_db
def test_server_unlimited_context_window():
    model = Model.objects.create(model_name="unlimited-model")
    s_unlimited = Server.objects.create(
        model_id=model.id,
        base_url="http://unlimited.example",
        is_online=True,
        context_window=None
    )
    
    # Should be returned regardless of token count
    assert len(ServerRepository.list_by_model_id(model.id, estimate_tokens=500)) == 1
    assert len(ServerRepository.list_by_model_id(model.id, estimate_tokens=1000000)) == 1

@pytest.mark.django_db
def test_parser_estimates_tokens_and_storage():
    parser = RequestParser()
    body = b'{"model":"test-model","prompt":"Hello world, this is a test prompt to estimate tokens."}'
    parsed = parser.parse(body)
    
    assert parsed.estimated_input_tokens > 0
    # It should be around len("Hello world...") * 0.22 or so, but definitely > 0
    assert parsed.estimated_input_tokens > 5 
