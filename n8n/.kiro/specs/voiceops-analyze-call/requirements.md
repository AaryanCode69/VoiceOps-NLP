# Requirements Document

## Introduction

This document specifies the requirements for a custom n8n community node called "VoiceOps Analyze Call". The node analyzes financial call recordings for fraud risk using VoiceOps AI and routes calls based on risk score through two distinct outputs. The system must accept audio files in multiple formats, submit them to a VoiceOps FastAPI endpoint for analysis, poll for completion, and route execution based on configurable risk thresholds.

## Glossary

- **Node**: A single processing unit in n8n workflow automation that performs a specific operation
- **VoiceOps_System**: The custom n8n community node that analyzes call recordings for fraud risk
- **Audio_Input**: Audio file data provided as binary data, file path, or URL
- **Risk_Score**: A numerical value (0-100) indicating the likelihood of fraud in a call recording
- **Risk_Threshold**: A configurable value (0-100) used to determine routing between High Risk and Normal outputs
- **Call_ID**: A unique identifier generated for each audio analysis request
- **Poll_Timeout**: Maximum time in seconds to wait for analysis completion
- **Poll_Interval**: Time in seconds between polling attempts
- **High_Risk_Output**: Output 0 of the node, receives items with risk_score >= risk_threshold
- **Normal_Output**: Output 1 of the node, receives items with risk_score < risk_threshold
- **VoiceOps_API**: The FastAPI backend service that performs audio analysis
- **Analysis_Response**: JSON payload returned by VoiceOps API containing fraud analysis results
- **Multipart_Form_Data**: HTTP content type used for uploading audio files
- **NodeOperationError**: n8n's standard error type for runtime failures
- **ContinueOnFail**: n8n feature that allows workflow execution to continue despite node errors

## Requirements

### Requirement 1: Audio Input Handling

**User Story:** As a workflow developer, I want to provide audio files in multiple formats, so that I can integrate the node with various data sources.

#### Acceptance Criteria

1. WHEN a user selects binary input mode, THE VoiceOps_System SHALL accept audio data from the specified binary property
2. WHEN a user selects file path input mode, THE VoiceOps_System SHALL read audio data from the specified file system path
3. WHEN a user selects URL input mode, THE VoiceOps_System SHALL download audio data from the specified URL
4. WHEN an audio file exceeds 100MB, THE VoiceOps_System SHALL reject the file and return an error before sending to VoiceOps_API
5. WHERE binary input mode is selected, THE VoiceOps_System SHALL use a configurable binary property name with default value "data"
6. THE VoiceOps_System SHALL preserve the original filename when available during audio submission

### Requirement 2: VoiceOps API Integration

**User Story:** As a workflow developer, I want the node to communicate with VoiceOps API, so that I can analyze call recordings for fraud risk.

#### Acceptance Criteria

1. WHEN submitting audio for analysis, THE VoiceOps_System SHALL send a POST request to /api/v1/analyze-call using multipart/form-data encoding
2. WHEN submitting audio for analysis, THE VoiceOps_System SHALL generate a unique Call_ID for the request
3. WHEN submitting audio for analysis, THE VoiceOps_System SHALL include the audio file in the multipart request
4. WHERE a language is specified, THE VoiceOps_System SHALL include the language parameter in the analysis request
5. THE VoiceOps_System SHALL use the configured base URL from credentials for all API requests
6. WHERE an API key is configured, THE VoiceOps_System SHALL include it in API request headers
7. THE VoiceOps_System SHALL use this.helpers.httpRequest() for all HTTP communications

### Requirement 3: Analysis Polling

**User Story:** As a workflow developer, I want the node to wait for analysis completion, so that I can receive complete fraud analysis results.

#### Acceptance Criteria

1. WHEN audio is submitted successfully, THE VoiceOps_System SHALL poll GET /api/v1/result/{call_id} for analysis completion
2. WHILE polling for results, THE VoiceOps_System SHALL wait Poll_Interval seconds between each polling attempt
3. WHEN the polling response status is "processing", THE VoiceOps_System SHALL continue polling
4. WHEN the polling response status is "complete", THE VoiceOps_System SHALL proceed with result processing
5. WHEN the polling response status is "failed", THE VoiceOps_System SHALL throw a NodeOperationError with failure details
6. WHEN Poll_Timeout seconds have elapsed without completion, THE VoiceOps_System SHALL throw a NodeOperationError including the Call_ID
7. THE VoiceOps_System SHALL use configurable Poll_Timeout with default value 300 seconds
8. THE VoiceOps_System SHALL use configurable Poll_Interval with default value 5 seconds

### Requirement 4: Risk-Based Routing

**User Story:** As a workflow developer, I want calls routed to different outputs based on risk score, so that I can handle high-risk and normal calls differently.

#### Acceptance Criteria

1. WHEN Risk_Score is greater than or equal to Risk_Threshold, THE VoiceOps_System SHALL route the item exclusively to High_Risk_Output
2. WHEN Risk_Score is less than Risk_Threshold, THE VoiceOps_System SHALL route the item exclusively to Normal_Output
3. THE VoiceOps_System SHALL never send the same item to both outputs
4. THE VoiceOps_System SHALL use a configurable Risk_Threshold with default value 65
5. THE VoiceOps_System SHALL support Risk_Threshold values between 0 and 100 inclusive
6. WHEN Risk_Score is missing from Analysis_Response, THE VoiceOps_System SHALL default Risk_Score to 0 and route to Normal_Output

### Requirement 5: Output Data Enrichment

**User Story:** As a workflow developer, I want enriched output data with metadata and flattened fields, so that I can easily use the results in downstream nodes like Slack and Google Sheets.

#### Acceptance Criteria

1. THE VoiceOps_System SHALL add a _voiceops_meta object to each output item containing risk_threshold_used, is_high_risk, routed_to, and processed_at fields
2. THE VoiceOps_System SHALL flatten risk_score to the top level of the output JSON
3. THE VoiceOps_System SHALL flatten fraud_likelihood to the top level of the output JSON
4. THE VoiceOps_System SHALL flatten call_id to the top level of the output JSON
5. THE VoiceOps_System SHALL flatten explanation to the top level of the output JSON
6. THE VoiceOps_System SHALL flatten recommended_action to the top level of the output JSON
7. THE VoiceOps_System SHALL flatten matched_patterns to the top level of the output JSON
8. THE VoiceOps_System SHALL preserve the complete original Analysis_Response structure in the output
9. WHEN Risk_Score is missing from Analysis_Response, THE VoiceOps_System SHALL include a warning in _voiceops_meta

### Requirement 6: Error Handling

**User Story:** As a workflow developer, I want robust error handling, so that I can diagnose issues and optionally continue workflow execution despite errors.

#### Acceptance Criteria

1. WHEN a runtime error occurs, THE VoiceOps_System SHALL throw a NodeOperationError with descriptive error message
2. WHERE ContinueOnFail is enabled and an error occurs, THE VoiceOps_System SHALL push an error object to Normal_Output instead of throwing
3. WHERE ContinueOnFail is enabled and an error occurs, THE VoiceOps_System SHALL not throw an exception
4. WHEN a network error occurs, THE VoiceOps_System SHALL include HTTP status code in the error message
5. WHEN an error occurs after Call_ID generation, THE VoiceOps_System SHALL include the Call_ID in the error message
6. WHEN audio validation fails, THE VoiceOps_System SHALL provide an actionable error message indicating the validation failure reason
7. THE VoiceOps_System SHALL never use console.log for error reporting

### Requirement 7: Independent Item Processing

**User Story:** As a workflow developer, I want each input item processed independently, so that one item's failure doesn't affect other items.

#### Acceptance Criteria

1. THE VoiceOps_System SHALL process each input item independently without sharing state
2. THE VoiceOps_System SHALL not batch multiple audio files into a single API request
3. WHEN processing multiple input items, THE VoiceOps_System SHALL generate a unique Call_ID for each item
4. WHEN one item fails processing, THE VoiceOps_System SHALL continue processing remaining items

### Requirement 8: Node Configuration

**User Story:** As a workflow developer, I want to configure the node through credentials and parameters, so that I can adapt it to different environments and use cases.

#### Acceptance Criteria

1. THE VoiceOps_System SHALL require a voiceOpsApi credential containing baseUrl
2. WHERE provided, THE VoiceOps_System SHALL use apiKey from voiceOpsApi credential
3. WHERE provided, THE VoiceOps_System SHALL use webhookSecret from voiceOpsApi credential
4. THE VoiceOps_System SHALL provide a parameter to select audio source mode (binary, filePath, url)
5. THE VoiceOps_System SHALL provide a parameter to configure Risk_Threshold
6. THE VoiceOps_System SHALL provide advanced parameters for Poll_Timeout and Poll_Interval
7. THE VoiceOps_System SHALL provide an advanced parameter to force language selection (auto, en, hi, hi-en)
8. THE VoiceOps_System SHALL use default value "binary" for audio source mode
9. THE VoiceOps_System SHALL use default value "data" for binary property name
10. THE VoiceOps_System SHALL never contain hardcoded URLs, secrets, or threshold values

### Requirement 9: n8n Architecture Compliance

**User Story:** As an n8n platform, I want the node to follow community node conventions, so that it integrates seamlessly with the n8n ecosystem.

#### Acceptance Criteria

1. THE VoiceOps_System SHALL have exactly one input
2. THE VoiceOps_System SHALL have exactly two outputs
3. THE VoiceOps_System SHALL name outputs "High Risk" and "Normal" respectively
4. THE VoiceOps_System SHALL use displayName "VoiceOps Analyze Call"
5. THE VoiceOps_System SHALL use name "voiceOpsAnalyzeCall"
6. THE VoiceOps_System SHALL use group ['transform']
7. THE VoiceOps_System SHALL use version 1
8. THE VoiceOps_System SHALL provide description "Analyzes financial call recordings for fraud risk using VoiceOps AI and routes calls by risk score"
9. THE VoiceOps_System SHALL be implemented in TypeScript with strict typing
10. THE VoiceOps_System SHALL avoid using 'any' type unless unavoidable

### Requirement 10: Downstream Compatibility

**User Story:** As a workflow developer, I want the node output to work seamlessly with Slack and Google Sheets nodes, so that I can build complete workflows without data transformation.

#### Acceptance Criteria

1. WHEN output is sent to Slack node, THE VoiceOps_System SHALL provide flattened fields that Slack can directly reference
2. WHEN output is sent to Google Sheets node, THE VoiceOps_System SHALL provide flattened fields that can be directly mapped to columns
3. THE VoiceOps_System SHALL ensure all flattened fields use consistent naming conventions compatible with downstream nodes
