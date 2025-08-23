# Requirements Document

## Introduction

This feature implements a Python-based Twitch chatbot that integrates with Ollama to generate contextually relevant chat messages. The primary function is to analyze recent chat messages and generate messages that a typical user might say, creating natural conversation flow. The bot will also support responding to direct messages while considering recent chat context. The system connects to Twitch IRC, maintains chat history, and uses locally hosted language models through Ollama for message generation.

## Requirements

### Requirement 1

**User Story:** As a Twitch streamer, I want to deploy a chatbot that can operate in multiple channels simultaneously, generating natural chat messages based on each channel's unique conversation context, so that I can maintain chat activity across different streams.

#### Acceptance Criteria

1. WHEN the bot is started THEN the system SHALL connect to Twitch IRC and join multiple configured channels
2. WHEN viewers send messages in any channel THEN the bot SHALL collect and store message history separately for each channel
3. WHEN generating a message for a channel THEN the system SHALL use only that channel's recent chat context with Ollama
4. WHEN Ollama returns a generated message THEN the bot SHALL send it to the appropriate channel
5. IF the Twitch connection fails THEN the system SHALL attempt to reconnect and rejoin all configured channels

### Requirement 2

**User Story:** As a streamer, I want to configure when and how the bot generates messages using message count thresholds and time delays, so that I can control the bot's participation level and prevent spam in my chat.

#### Acceptance Criteria

1. WHEN the bot is configured THEN the system SHALL use message count thresholds to trigger automatic message generation (default: 30 messages)
2. WHEN the message count threshold is reached THEN the system SHALL enforce a minimum time delay since the last bot message before generating (default: 5 minutes)
3. WHEN configuring the bot THEN the system SHALL allow customizing both the message count threshold and minimum time delay per channel
4. WHEN the bot generates a message THEN the system SHALL reset the message counter and timestamp for that channel
5. WHEN insufficient chat history exists for automatic generation THEN the system SHALL wait until the context window is adequately populated before generating spontaneous messages

### Requirement 3

**User Story:** As a streamer, I want to configure Ollama integration per channel, so that I can customize the AI model for each channel's specific audience while using a shared Ollama server.

#### Acceptance Criteria

1. WHEN configuring the bot per channel THEN the system SHALL allow selecting which Ollama model to use for that channel
2. WHEN no channel-specific model is configured THEN the system SHALL use the global default Ollama model
3. WHEN configuring message generation THEN the system SHALL allow setting message length limits per channel
4. WHEN switching models THEN the system SHALL validate that the specified model is available on the Ollama server
5. IF Ollama is unavailable THEN the bot SHALL handle the error gracefully and pause message generation until reconnected

### Requirement 4

**User Story:** As a streamer, I want the bot to respond contextually to direct mentions, so that viewers can interact with the AI while maintaining conversation relevance.

#### Acceptance Criteria

1. WHEN a message starts with "@<bot-username>" or "<bot-username>" (case-insensitive) THEN the system SHALL detect it as a direct mention
2. WHEN responding to a mention THEN the system SHALL include recent chat context along with the user's message in the Ollama prompt
3. WHEN generating a response THEN the system SHALL create contextually relevant replies that consider both the user's input and recent chat history
4. WHEN responding to mentions THEN the system SHALL bypass normal message count and time delay restrictions
5. WHEN responding THEN the system SHALL maintain the conversational flow and tone established by recent messages

### Requirement 5

**User Story:** As a streamer, I want to authenticate the bot using a dedicated Twitch bot account with persistent token storage, so that it can join and participate in my chat without requiring re-authentication on every startup.

#### Acceptance Criteria

1. WHEN setting up the bot THEN the system SHALL support Twitch OAuth authentication for a dedicated bot account
2. WHEN authenticating THEN the system SHALL securely store authentication tokens in the database and automatically detect the bot's username from the OAuth response
3. WHEN the bot starts THEN the system SHALL load stored tokens and validate authentication before connecting to channels
4. WHEN tokens expire THEN the system SHALL handle token refresh automatically and update the stored tokens
5. WHEN authentication fails THEN the system SHALL provide clear error messages and prompt for re-authentication

### Requirement 6

**User Story:** As a streamer, I want to manage chat history with persistent storage per channel, so that the bot generates relevant messages for each channel without cross-contamination.

#### Acceptance Criteria

1. WHEN collecting chat messages THEN the system SHALL store messages in a database (SQLite or MySQL) with channel isolation and configurable retention policies
2. WHEN generating messages for a channel THEN the system SHALL limit the context sent to Ollama to a maximum number of recent messages (default: 200 messages per channel)
3. WHEN the context exceeds the maximum limit THEN the system SHALL use only the most recent messages within the limit for generation
4. WHEN configuring retention policies THEN the system SHALL support automatic cleanup of old messages based on age or count limits per channel
5. WHEN querying messages THEN the system SHALL ensure strict channel isolation to prevent cross-contamination between channels

### Requirement 7

**User Story:** As a streamer, I want to monitor the bot's activity and performance, so that I can ensure it's working correctly and troubleshoot issues.

#### Acceptance Criteria

1. WHEN the bot is running THEN the system SHALL log all significant events and errors
2. WHEN the bot processes messages THEN the system SHALL track response times and success rates
3. WHEN errors occur THEN the system SHALL provide detailed error information for debugging
4. WHEN the bot is active THEN the system SHALL display connection status and message counts
5. IF performance degrades THEN the system SHALL alert the user or automatically adjust behavior

### Requirement 8

**User Story:** As a streamer, I want the bot to have mandatory content filtering on both input and output, so that inappropriate content never influences the bot's learning or gets sent to chat.

#### Acceptance Criteria

1. WHEN processing incoming chat messages THEN the system SHALL always filter inappropriate messages before storing them in the chat context
2. WHEN the bot generates a message THEN the system SHALL always scan the output for inappropriate language, hate speech, and harmful content
3. WHEN inappropriate content is detected in bot output THEN the system SHALL block the message from being sent and log the blocked content with full context for debugging
4. WHEN configuring content filtering THEN the system SHALL allow customizing filtering rules and blocked word lists for both input and output filtering
5. WHEN content filtering fails or is unavailable THEN the system SHALL default to blocking suspicious content rather than allowing it through

### Requirement 9

**User Story:** As a streamer, I want the bot to respect moderation actions by removing content from banned users or deleted messages from its context, so that it doesn't learn from or reference inappropriate content that was already moderated.

#### Acceptance Criteria

1. WHEN a user is banned or timed out THEN the system SHALL remove all messages from that user from the current chat context
2. WHEN a message is deleted by moderators THEN the system SHALL remove that specific message from the chat context
3. WHEN purging messages THEN the system SHALL update the context window to exclude the removed content
4. WHEN moderation events occur THEN the system SHALL log the context cleanup actions for debugging
5. IF the bot has already referenced removed content in recent messages THEN the system SHALL avoid repeating similar patterns

### Requirement 10

**User Story:** As a streamer, I want a flexible configuration system with chat commands that allows global defaults and per-channel customization, so that I can easily manage bot behavior across multiple channels with different requirements.

#### Acceptance Criteria

1. WHEN deploying the bot THEN the system SHALL use environment variables for global configuration (Ollama server URL, database settings, OAuth tokens, default Ollama model)
2. WHEN the bot joins a channel THEN the system SHALL load channel-specific settings from the database, falling back to global defaults
3. WHEN moderators or channel owners send commands in the format "!clank <setting>" THEN the system SHALL display the current value of that setting
4. WHEN moderators or channel owners send commands in the format "!clank <setting> <value>" THEN the system SHALL update the channel-specific setting and confirm the change
5. WHEN non-authorized users attempt configuration commands THEN the system SHALL ignore the commands and optionally notify about insufficient permissions

### Requirement 11

**User Story:** As a streamer, I want the bot to generate properly formatted single messages that comply with Twitch's message limits, so that all generated content is successfully delivered to chat.

#### Acceptance Criteria

1. WHEN prompting Ollama THEN the system SHALL request generation of exactly one chat message
2. WHEN Ollama returns a response THEN the system SHALL ensure the message is 500 characters or less (Twitch's limit)
3. WHEN a generated message exceeds the character limit THEN the system SHALL truncate it appropriately while maintaining readability
4. WHEN generating messages THEN the system SHALL strip any formatting or special characters that Twitch doesn't support
5. WHEN Ollama returns multiple messages or invalid format THEN the system SHALL extract or reformat to a single valid chat message

### Requirement 12

**User Story:** As a streamer, I want the bot to handle Ollama errors gracefully without disrupting chat, so that temporary AI service issues don't cause spam or unwanted behavior.

#### Acceptance Criteria

1. WHEN Ollama is offline or unreachable THEN the system SHALL skip message generation attempts and remain silent
2. WHEN making requests to Ollama THEN the system SHALL enforce a timeout limit (default: 30 seconds)
3. WHEN Ollama requests timeout or fail THEN the system SHALL log the error and skip that generation cycle
4. WHEN Ollama returns invalid or empty responses THEN the system SHALL remain silent rather than send fallback messages
5. WHEN Ollama becomes available again THEN the system SHALL resume normal message generation without queuing missed attempts

### Requirement 13

**User Story:** As a streamer, I want the bot to maintain consistent context handling and configuration across restarts, so that it can resume normal operation seamlessly without losing conversation continuity.

#### Acceptance Criteria

1. WHEN the bot starts THEN the system SHALL load the configured context window size of recent messages from the database for each channel
2. WHEN the bot restarts THEN the system SHALL continue message counting from where it left off in the previous session and load recent chat history for each channel separately to maintain context continuity
3. WHEN generating automatic messages THEN the system SHALL only generate if adequate context is available
4. WHEN responding to direct mentions THEN the system SHALL always attempt to respond using whatever context is available, even if limited
5. WHEN configuring the bot THEN the system SHALL allow customizing the context window size per channel



