# Twitch Ollama Chatbot - Test Suite

This directory contains a comprehensive test suite for the Twitch Ollama Chatbot, covering unit tests, integration tests, and performance tests.

## Test Structure

```
tests/
├── conftest.py                          # Shared fixtures and test configuration
├── requirements.txt                     # Test dependencies
├── run_tests.py                        # Test runner script
├── README.md                           # This file
├── test_database_manager.py            # Unit tests for database operations
├── test_ollama_client.py               # Unit tests for Ollama API client
├── test_content_filter.py              # Unit tests for content filtering
├── test_configuration_manager.py       # Unit tests for configuration management
├── test_integration_message_flow.py    # Integration tests for message processing
├── test_integration_chat_commands.py   # Integration tests for chat commands
└── test_performance.py                 # Performance and load tests
```

## Test Categories

### Unit Tests
- **Database Manager** (`test_database_manager.py`)
  - Message storage and retrieval
  - Channel configuration management
  - Database connection handling
  - Error recovery and resilience
  - Channel isolation
  - Message cleanup and moderation

- **Ollama Client** (`test_ollama_client.py`)
  - API communication and error handling
  - Model validation and management
  - Message generation (spontaneous and response)
  - Service availability monitoring
  - Resilience and graceful degradation
  - Response validation and formatting

- **Content Filter** (`test_content_filter.py`)
  - Blocked word loading and management
  - Input and output filtering
  - Text normalization and evasion detection
  - Performance with large word lists
  - Unicode and special character handling

- **Configuration Manager** (`test_configuration_manager.py`)
  - Chat command processing
  - User permission validation
  - Configuration validation and persistence
  - Status reporting
  - Model validation integration

### Integration Tests
- **Message Processing Flow** (`test_integration_message_flow.py`)
  - Complete message processing pipeline
  - Content filtering integration
  - Generation trigger logic
  - Cooldown management
  - Moderation event handling
  - Channel isolation
  - Error handling and recovery

- **Chat Commands** (`test_integration_chat_commands.py`)
  - End-to-end command processing
  - Configuration persistence
  - Permission system integration
  - Status reporting with real components
  - Multi-channel configuration
  - Concurrent command processing

### Performance Tests
- **Database Performance** (`test_performance.py`)
  - Message storage and retrieval performance
  - Concurrent operation handling
  - Large dataset management
  - Cleanup operation efficiency
  - Memory usage optimization
  - Context window building performance

## Running Tests

### Prerequisites

1. Install test dependencies:
```bash
pip install -r tests/requirements.txt
```

2. Ensure the main application dependencies are installed:
```bash
pip install -r requirements.txt
```

### Using the Test Runner

The easiest way to run tests is using the provided test runner:

```bash
# Run all tests
python tests/run_tests.py

# Run only unit tests
python tests/run_tests.py --type unit

# Run only integration tests
python tests/run_tests.py --type integration

# Run only performance tests
python tests/run_tests.py --type performance

# Run tests with coverage report
python tests/run_tests.py --coverage

# Run tests in parallel
python tests/run_tests.py --parallel

# Run tests with verbose output
python tests/run_tests.py --verbose

# Skip slow performance tests
python tests/run_tests.py --fast

# Generate HTML coverage report
python tests/run_tests.py --coverage --html-report
```

### Using Pytest Directly

You can also run tests directly with pytest:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_database_manager.py

# Run specific test class
pytest tests/test_database_manager.py::TestDatabaseManager

# Run specific test method
pytest tests/test_database_manager.py::TestDatabaseManager::test_store_message_success

# Run with coverage
pytest --cov=chatbot --cov-report=html

# Run in parallel
pytest -n auto

# Run with verbose output
pytest -v
```

### Test Markers

Tests are marked with categories for selective execution:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only performance tests
pytest -m performance

# Skip slow tests
pytest -m "not slow"
```

## Test Configuration

### Fixtures

The test suite uses several shared fixtures defined in `conftest.py`:

- **Database fixtures**: `db_manager`, `channel_config_manager`
- **Mock fixtures**: `mock_ollama_client`, `content_filter`
- **Test data fixtures**: `sample_message_event`, `sample_messages`
- **Temporary files**: `temp_db_file`, `temp_blocked_words_file`

### Environment Setup

Tests automatically create temporary databases and configuration files, so no manual setup is required. Each test runs in isolation with its own temporary resources.

### Async Test Support

The test suite fully supports async/await patterns using `pytest-asyncio`. All async tests are automatically detected and run properly.

## Coverage Reporting

### Generating Coverage Reports

```bash
# Terminal coverage report
python tests/run_tests.py --coverage

# HTML coverage report
python tests/run_tests.py --coverage --html-report

# View HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Targets

The test suite aims for:
- **Overall coverage**: >90%
- **Core components**: >95%
- **Critical paths**: 100%

### Coverage Exclusions

The following are excluded from coverage requirements:
- Test files themselves
- Abstract methods and protocols
- Debug/development code
- Error handling for impossible conditions

## Performance Testing

### Performance Benchmarks

Performance tests validate that the system meets these benchmarks:

- **Message storage**: >30 messages/second
- **Message retrieval**: <100ms for 200 messages
- **Content filtering**: >1000 operations/second
- **Database cleanup**: <5 seconds for 2000 messages
- **Context building**: <50ms for 200 messages

### Performance Test Categories

1. **Database Performance**
   - Sequential and concurrent message storage
   - Message retrieval with various limits
   - Cleanup operations
   - Multi-channel isolation

2. **Context Window Performance**
   - Context building with large message histories
   - Memory efficiency with concurrent operations
   - Large context window handling

3. **Content Filter Performance**
   - Filtering operations with various message lengths
   - Blocked word loading with large lists
   - Unicode and special character handling

### Running Performance Tests

```bash
# Run only performance tests
python tests/run_tests.py --type performance

# Skip performance tests (for faster CI)
python tests/run_tests.py --fast
```

## Continuous Integration

### GitHub Actions

The test suite is designed to work with GitHub Actions:

```yaml
- name: Run Tests
  run: |
    pip install -r tests/requirements.txt
    python tests/run_tests.py --coverage --parallel
```

### Test Parallelization

Tests can be run in parallel using `pytest-xdist`:

```bash
# Automatic parallel execution
pytest -n auto

# Specific number of workers
pytest -n 4
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure you're running tests from the project root
   - Check that all dependencies are installed

2. **Database Errors**
   - Tests use temporary databases that are automatically cleaned up
   - If tests fail, check file permissions in the temp directory

3. **Async Test Issues**
   - Ensure `pytest-asyncio` is installed
   - Check that async fixtures are properly awaited

4. **Performance Test Failures**
   - Performance tests may fail on slow systems
   - Consider adjusting performance thresholds for your environment

### Debug Mode

Run tests with maximum verbosity for debugging:

```bash
pytest -vvv --tb=long --capture=no
```

### Test Data

Tests use realistic but synthetic data:
- Message content reflects typical Twitch chat patterns
- User names and IDs are generated consistently
- Timestamps are controlled for predictable ordering

## Contributing

When adding new tests:

1. **Follow naming conventions**: `test_*.py` files, `test_*` functions
2. **Use appropriate fixtures**: Leverage existing fixtures when possible
3. **Add docstrings**: Explain what each test validates
4. **Consider performance**: Mark slow tests appropriately
5. **Test error conditions**: Include negative test cases
6. **Maintain isolation**: Tests should not depend on each other

### Test Categories

- Mark unit tests with `@pytest.mark.unit`
- Mark integration tests with `@pytest.mark.integration`
- Mark performance tests with `@pytest.mark.performance`
- Mark slow tests with `@pytest.mark.slow`

### Example Test Structure

```python
import pytest
from unittest.mock import Mock, AsyncMock

class TestMyComponent:
    """Test cases for MyComponent class."""
    
    @pytest.mark.asyncio
    async def test_my_feature_success(self, my_fixture):
        """Test successful operation of my feature."""
        # Arrange
        component = MyComponent()
        
        # Act
        result = await component.my_method()
        
        # Assert
        assert result is not None
        assert result.status == "success"
    
    @pytest.mark.asyncio
    async def test_my_feature_error_handling(self, my_fixture):
        """Test error handling in my feature."""
        # Test error conditions
        pass
```

This comprehensive test suite ensures the reliability, performance, and correctness of the Twitch Ollama Chatbot across all its components and use cases.