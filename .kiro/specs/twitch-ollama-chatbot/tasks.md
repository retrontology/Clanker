# Implementation Plan

- [x] 1. Set up project structure and core dependencies
  - Create Python project directory structure with modular architecture
  - Set up requirements.txt with TwitchIO, aiohttp, SQLAlchemy, python-dotenv, and logging dependencies
  - Create main entry point and basic configuration loading from environment variables
  - _Requirements: 1.1, 5.1, 10.1_

- [x] 2. Implement database layer with schema and connection management
  - [x] 2.1 Create database schema and migration system
    - Write SQL schema for messages, channel_config, user_response_cooldowns, bot_metrics, and auth_tokens tables
    - Implement database initialization and schema creation for both SQLite and MySQL
    - Create indexes for optimal query performance on channel/timestamp combinations
    - _Requirements: 6.1, 6.3, 6.4_
  
  - [x] 2.2 Implement DatabaseManager with connection handling
    - Code DatabaseManager class with factory pattern for SQLite/MySQL selection
    - Implement connection pooling, retry logic, and graceful failure handling
    - Write methods for storing messages, retrieving recent messages, and handling moderation events
    - _Requirements: 6.1, 6.2, 9.1, 9.2, 9.3_
  
  - [x] 2.3 Create ChannelConfigManager for per-channel settings
    - Implement channel configuration storage and retrieval with database persistence
    - Code message counting, cooldown tracking, and persistent state management across restarts
    - Write methods for loading and saving channel state during startup and shutdown
    - _Requirements: 2.1, 2.2, 2.4, 10.2, 13.1, 13.2_

- [x] 3. Implement authentication and OAuth token management
  - [x] 3.1 Create AuthenticationManager with token storage
    - Implement OAuth token storage in database with encryption for sensitive data
    - Code automatic token refresh logic with retry handling and graceful failure
    - Write username detection from OAuth response and token validation methods
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [x] 3.2 Implement startup authentication validation
    - Code authentication validation during bot startup with clear error messaging
    - Implement token refresh attempts and graceful shutdown on authentication failure
    - Write logging for authentication events and token refresh operations
    - _Requirements: 5.3, 5.4, 5.5_

- [x] 4. Create content filtering system with configurable word lists
  - [x] 4.1 Implement ContentFilter class with blocked words loading
    - Code content filtering with customizable blocked words file and normalization techniques
    - Implement input and output filtering with fail-safe blocking behavior
    - Write text normalization to handle leetspeak, spacing tricks, and evasion attempts
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [x] 4.2 Create blocked words configuration and filtering logic
    - Implement blocked words file format with comments and category organization
    - Code filtering philosophy that allows mild profanity but blocks hate speech and slurs
    - Write filtering integration points for both input processing and output validation
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 5. Implement Ollama client with dual prompt system
  - [x] 5.1 Create OllamaClient with HTTP communication
    - Code HTTP client for Ollama API with timeout handling and error recovery
    - Implement model validation, health checking, and graceful failure handling
    - Write request/response handling with proper error logging and retry logic
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [x] 5.2 Implement dual prompt system for spontaneous vs response messages
    - Code separate prompt templates for spontaneous messages and mention responses
    - Implement context formatting differences for each message type
    - Write prompt selection logic based on generation context and user interaction
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [x] 5.3 Create message validation and formatting
    - Implement 500-character limit enforcement with intelligent truncation
    - Code response validation to ensure single message format and proper content
    - Write message formatting to strip unsupported characters and maintain readability
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 6. Implement TwitchIO IRC client with event handling
  - [x] 6.1 Create TwitchIRCClient with connection management
    - Code TwitchIO bot client with multi-channel support and automatic reconnection
    - Implement event handlers for messages, moderation events, and connection status
    - Write bot detection logic to filter out bot messages and system notifications
    - _Requirements: 1.1, 1.2, 1.5, 9.1, 9.2, 9.3_
  
  - [x] 6.2 Implement message processing and routing
    - Code message event processing with content filtering and database storage
    - Implement chat command detection and routing to configuration manager
    - Write mention detection logic for direct user interactions and responses
    - _Requirements: 1.2, 1.3, 4.1, 4.2, 10.3, 10.4_
  
  - [x] 6.3 Create moderation event handling
    - Implement CLEARMSG and CLEARCHAT event processing for message cleanup
    - Code user ban/timeout handling with context window updates
    - Write moderation event logging and database cleanup operations
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [ ] 7. Implement rate limiting with dual cooldown systems
  - [ ] 7.1 Create spontaneous message rate limiting
    - Code channel-level cooldown tracking for automatic message generation
    - Implement message count thresholds with configurable limits per channel
    - Write cooldown validation logic that considers both count and time constraints
    - _Requirements: 2.1, 2.2, 2.4, 2.5_
  
  - [ ] 7.2 Implement per-user response rate limiting
    - Code user-specific cooldown tracking for mention responses in database
    - Implement independent rate limiting that doesn't affect spontaneous generation
    - Write cooldown management with database persistence and cleanup
    - _Requirements: 4.4, 4.5_

- [ ] 8. Create configuration management with chat commands
  - [ ] 8.1 Implement ConfigurationManager with command processing
    - Code chat command parsing and validation for !clank commands
    - Implement user authorization checking using Twitch IRC badges
    - Write configuration validation and error handling for invalid settings
    - _Requirements: 10.3, 10.4, 10.5_
  
  - [ ] 8.2 Create global and per-channel configuration system
    - Implement environment variable loading for global settings
    - Code database-backed per-channel configuration with immediate updates
    - Write configuration persistence and loading during startup
    - _Requirements: 10.1, 10.2, 3.3_
  
  - [ ] 8.3 Implement status monitoring commands
    - Code !clank status command for Ollama connectivity and performance stats
    - Implement system health reporting with model information and response times
    - Write status command authorization and informative response formatting
    - _Requirements: 7.1, 7.2, 7.4_

- [ ] 9. Implement message processing coordinator
  - [ ] 9.1 Create MessageProcessor with generation triggers
    - Code message processing flow from IRC to database to generation
    - Implement trigger logic for spontaneous message generation based on thresholds
    - Write generation coordination between database context and Ollama client
    - _Requirements: 1.3, 1.4, 2.3, 2.5_
  
  - [ ] 9.2 Implement context window management
    - Code context retrieval with configurable limits and channel isolation
    - Implement context window building with proper message ordering and formatting
    - Write context management for both spontaneous and response generation scenarios
    - _Requirements: 6.2, 6.3, 13.3, 13.4, 13.5_

- [ ] 10. Create comprehensive logging and monitoring system
  - [ ] 10.1 Implement StructuredLogger with JSON and console formats
    - Code structured logging system with configurable output formats
    - Implement log levels (INFO, WARNING, ERROR, DEBUG) with appropriate event categorization
    - Write logging configuration with file rotation and security considerations
    - _Requirements: 7.1, 7.2, 7.3_
  
  - [ ] 10.2 Create performance metrics and monitoring
    - Code MetricsManager for tracking response times, success rates, and error counts
    - Implement performance data collection and storage in bot_metrics table
    - Write metrics cleanup and reporting functionality for system monitoring
    - _Requirements: 7.2, 7.4, 7.5_

- [ ] 11. Implement error recovery and resilience systems
  - [ ] 11.1 Create database connection resilience
    - Code exponential backoff reconnection logic with maximum delay limits
    - Implement graceful handling of partial database failures (read-only/write-only scenarios)
    - Write connection health monitoring and automatic recovery procedures
    - _Requirements: 12.1, 12.3, 12.5_
  
  - [ ] 11.2 Implement Ollama service resilience
    - Code graceful handling of Ollama unavailability with silent failure
    - Implement startup model validation with graceful exit on missing default model
    - Write runtime model validation for chat commands with error messaging
    - _Requirements: 3.4, 3.5, 12.1, 12.2, 12.4, 12.5_
  
  - [ ] 11.3 Create IRC connection resilience
    - Code indefinite reconnection attempts with exponential backoff
    - Implement banned channel tracking to respect moderation actions
    - Write connection state management and recovery logging
    - _Requirements: 1.5_

- [ ] 12. Create main application with startup sequence
  - [ ] 12.1 Implement main application entry point
    - Code application startup sequence with proper component initialization order
    - Implement graceful shutdown handling with cleanup and state persistence
    - Write startup validation for all required services and configurations
    - _Requirements: 1.1, 5.3, 13.1, 13.2_
  
  - [ ] 12.2 Create resource management and cleanup
    - Code ResourceManager for memory usage monitoring and automatic cleanup
    - Implement periodic cleanup tasks for old messages, metrics, and temporary data
    - Write resource exhaustion protection with configurable thresholds and limits
    - _Requirements: 6.4, 7.5_

- [ ] 13. Write comprehensive test suite
  - [ ] 13.1 Create unit tests for core components
    - Write unit tests for DatabaseManager, OllamaClient, ContentFilter, and ConfigurationManager
    - Implement mock objects for external services (Twitch IRC, Ollama API, database)
    - Code test cases for error handling, edge cases, and configuration validation
    - _Requirements: All requirements validation_
  
  - [ ] 13.2 Implement integration tests
    - Code integration tests for message processing flow from IRC to generation
    - Implement end-to-end tests for chat commands, rate limiting, and moderation events
    - Write performance tests for database operations and context window management
    - _Requirements: All requirements validation_

- [ ] 14. Create deployment configuration and documentation
  - [ ] 14.1 Create deployment scripts and configuration
    - Write Docker configuration for containerized deployment
    - Implement systemd service configuration for Linux deployment
    - Code environment variable templates and configuration examples
    - _Requirements: 10.1, 5.1_
  
  - [ ] 14.2 Write comprehensive documentation
    - Create installation and setup guide with OAuth configuration steps
    - Write configuration reference for all environment variables and chat commands
    - Code troubleshooting guide with common issues and error resolution
    - _Requirements: All requirements documentation_