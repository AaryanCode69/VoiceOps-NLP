# Implementation Plan: VoiceOps Analyze Call Node

## Overview

This implementation plan breaks down the VoiceOps Analyze Call n8n community node into discrete, incremental coding tasks. Each task builds on previous work, with property-based tests placed close to implementation to catch errors early. The node will accept audio files in multiple formats, submit them to VoiceOps API for fraud analysis, and route results through two outputs based on risk scores.

## Tasks

- [x] 1. Set up project structure and credentials
  - Create n8n-nodes-voiceops directory structure
  - Create VoiceOpsApi.credentials.ts with baseUrl, apiKey, and webhookSecret fields
  - Set up package.json with n8n dependencies and TypeScript configuration
  - Add fast-check as dev dependency for property-based testing
  - Create tsconfig.json with strict TypeScript settings
  - _Requirements: 8.1, 8.2, 8.3, 9.9, 9.10_

- [x] 2. Define TypeScript interfaces and types
  - Create interfaces for IVoiceOpsApiCredentials
  - Create interfaces for IVoiceOpsNodeParameters
  - Create interfaces for IAnalysisResponse with nested input_risk_assessment and rag_output
  - Create interfaces for IPollResponse with status union type
  - Create interfaces for IEnrichedOutput with flattened fields and _voiceops_meta
  - _Requirements: 9.9, 9.10_

- [x] 3. Implement node description and parameters
  - [x] 3.1 Create VoiceOpsAnalyzeCall.node.ts with INodeType implementation
    - Define node identity: displayName, name, icon, group, version, description
    - Configure inputs: ['main']
    - Configure outputs: ['main', 'main'] with outputNames: ['High Risk', 'Normal']
    - Link voiceOpsApi credentials
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_
  
  - [x] 3.2 Add audio source parameter with options (binary, filePath, url)
    - Set default to 'binary'
    - _Requirements: 8.4, 8.8_
  
  - [x] 3.3 Add conditional parameters for each audio source type
    - Binary property name (shown when audioSource = binary, default 'data')
    - Audio file path (shown when audioSource = filePath)
    - Audio URL (shown when audioSource = url)
    - _Requirements: 1.5, 8.9_
  
  - [x] 3.4 Add risk threshold parameter
    - Type: number, default: 65, min: 0, max: 100
    - _Requirements: 4.4, 4.5, 8.5_
  
  - [x] 3.5 Add advanced options collection
    - Poll timeout (default 300 seconds)
    - Poll interval (default 5 seconds)
    - Force language (options: auto, en, hi, hi-en)
    - _Requirements: 3.7, 3.8, 8.6, 8.7_

- [x] 4. Implement audio input handling
  - [x] 4.1 Create readBinaryInput() function
    - Read audio from items[i].binary[binaryPropertyName]
    - Preserve filename from binary metadata
    - Return audio buffer and filename
    - _Requirements: 1.1, 1.5, 1.6_
  
  - [x] 4.2 Create readFilePathInput() function
    - Read audio from file system using Node.js fs module
    - Extract filename from path
    - Return audio buffer and filename
    - _Requirements: 1.2, 1.6_
  
  - [x] 4.3 Create readUrlInput() function
    - Download audio using this.helpers.httpRequest()
    - Extract filename from URL or Content-Disposition header
    - Return audio buffer and filename
    - _Requirements: 1.3, 1.6_
  
  - [x] 4.4 Create validateFileSize() function
    - Check if audio buffer size exceeds 100MB (104857600 bytes)
    - Throw NodeOperationError with descriptive message if exceeded
    - _Requirements: 1.4, 6.1, 6.6_
  
  - [ ]* 4.5 Write property test for audio input mode routing
    - **Property 1: Audio Input Mode Routing**
    - **Validates: Requirements 1.1, 1.2, 1.3**
  
  - [ ]* 4.6 Write property test for binary property name configuration
    - **Property 2: Binary Property Name Configuration**
    - **Validates: Requirements 1.5**
  
  - [ ]* 4.7 Write property test for filename preservation
    - **Property 3: Filename Preservation**
    - **Validates: Requirements 1.6**

- [ ] 5. Implement Call ID generation and API submission
  - [x] 5.1 Create generateCallId() function using uuid v4
    - Import uuid library
    - Return unique UUID string
    - _Requirements: 2.2_
  
  - [x] 5.2 Create submitAudioForAnalysis() function
    - Build multipart/form-data request with audio file and call_id
    - Include language parameter if specified
    - Use configured baseUrl from credentials
    - Include apiKey in headers if configured
    - POST to /api/v1/analyze-call using this.helpers.httpRequest()
    - Handle network errors with HTTP status codes
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 6.4_
  
  - [ ]* 5.3 Write property test for Call ID uniqueness
    - **Property 5: Call ID Uniqueness**
    - **Validates: Requirements 2.2**
  
  - [ ]* 5.4 Write property test for multipart request format
    - **Property 4: Multipart Request Format**
    - **Validates: Requirements 2.1**
  
  - [ ]* 5.5 Write property test for audio inclusion in request
    - **Property 6: Audio Inclusion in Request**
    - **Validates: Requirements 2.3**
  
  - [ ]* 5.6 Write property test for conditional language parameter
    - **Property 7: Conditional Language Parameter**
    - **Validates: Requirements 2.4**
  
  - [ ]* 5.7 Write property test for base URL configuration usage
    - **Property 8: Base URL Configuration Usage**
    - **Validates: Requirements 2.5**
  
  - [ ]* 5.8 Write property test for conditional API key header
    - **Property 9: Conditional API Key Header**
    - **Validates: Requirements 2.6**

- [x] 6. Checkpoint - Ensure audio handling and submission work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement polling mechanism
  - [x] 7.1 Create pollForResults() function
    - Accept call_id, pollTimeout, and pollInterval parameters
    - Track elapsed time from start
    - Loop: GET /api/v1/result/{call_id} using this.helpers.httpRequest()
    - Parse response status: processing, complete, failed
    - If processing: wait pollInterval seconds and continue
    - If complete: return analysis result
    - If failed: throw NodeOperationError with failure details
    - If timeout exceeded: throw NodeOperationError with call_id
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.1, 6.5_
  
  - [ ]* 7.2 Write property test for polling endpoint correctness
    - **Property 10: Polling Endpoint Correctness**
    - **Validates: Requirements 3.1**
  
  - [ ]* 7.3 Write property test for poll interval timing
    - **Property 11: Poll Interval Timing**
    - **Validates: Requirements 3.2**
  
  - [ ]* 7.4 Write property test for processing status continuation
    - **Property 12: Processing Status Continuation**
    - **Validates: Requirements 3.3**
  
  - [ ]* 7.5 Write property test for complete status processing
    - **Property 13: Complete Status Processing**
    - **Validates: Requirements 3.4**
  
  - [ ]* 7.6 Write property test for failed status error handling
    - **Property 14: Failed Status Error Handling**
    - **Validates: Requirements 3.5**
  
  - [ ]* 7.7 Write property test for timeout error handling
    - **Property 15: Timeout Error Handling**
    - **Validates: Requirements 3.6**
  
  - [ ]* 7.8 Write unit tests for polling configuration defaults
    - Test default pollTimeout of 300 seconds
    - Test default pollInterval of 5 seconds
    - _Requirements: 3.7, 3.8_

- [x] 8. Implement response processing and enrichment
  - [x] 8.1 Create extractRiskScore() function
    - Extract risk_score from input_risk_assessment
    - Return risk_score or undefined if missing
    - _Requirements: 4.6_
  
  - [x] 8.2 Create enrichWithMetadata() function
    - Create _voiceops_meta object with risk_threshold_used, is_high_risk, routed_to, processed_at
    - Add warning field if risk_score was missing
    - Add metadata to output item
    - _Requirements: 5.1, 5.9_
  
  - [x] 8.3 Create flattenKeyFields() function
    - Extract and flatten risk_score, fraud_likelihood, call_id to top level
    - Extract and flatten explanation, recommended_action, matched_patterns to top level
    - Preserve original nested structure
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_
  
  - [ ]* 8.4 Write property test for missing risk score handling
    - **Property 17: Missing Risk Score Handling**
    - **Validates: Requirements 4.6, 5.9**
  
  - [ ]* 8.5 Write property test for metadata enrichment
    - **Property 18: Metadata Enrichment**
    - **Validates: Requirements 5.1**
  
  - [ ]* 8.6 Write property test for field flattening completeness
    - **Property 19: Field Flattening Completeness**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6, 5.7**
  
  - [ ]* 8.7 Write property test for original structure preservation
    - **Property 20: Original Structure Preservation**
    - **Validates: Requirements 5.8**

- [x] 9. Implement risk-based routing logic
  - [x] 9.1 Create routeByRiskScore() function
    - Accept risk_score (with default 0 if missing), risk_threshold, and enriched item
    - If risk_score >= risk_threshold: return item for High Risk output (index 0)
    - If risk_score < risk_threshold: return item for Normal output (index 1)
    - Ensure mutual exclusivity (never both outputs)
    - _Requirements: 4.1, 4.2, 4.3, 4.6_
  
  - [ ]* 9.2 Write property test for risk-based routing correctness
    - **Property 16: Risk-Based Routing Correctness**
    - **Validates: Requirements 4.1, 4.2, 4.3**
  
  - [ ]* 9.3 Write unit tests for routing boundary conditions
    - Test risk_score exactly at threshold
    - Test risk_score at 0 and 100
    - Test threshold at 0 and 100
    - _Requirements: 4.1, 4.2, 4.5_

- [ ] 10. Checkpoint - Ensure routing and enrichment work correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement error handling
  - [x] 11.1 Add try-catch blocks in execute() method
    - Wrap item processing in try-catch
    - Check continueOnFail setting
    - If continueOnFail false: throw NodeOperationError
    - If continueOnFail true: push error object to Normal output
    - Include call_id in errors when available
    - Include HTTP status codes in network errors
    - _Requirements: 6.1, 6.2, 6.4, 6.5_
  
  - [ ]* 11.2 Write property test for error type correctness
    - **Property 21: Error Type Correctness**
    - **Validates: Requirements 6.1**
  
  - [ ]* 11.3 Write property test for continueOnFail error routing
    - **Property 22: ContinueOnFail Error Routing**
    - **Validates: Requirements 6.2**
  
  - [ ]* 11.4 Write property test for network error status code inclusion
    - **Property 23: Network Error Status Code Inclusion**
    - **Validates: Requirements 6.4**
  
  - [ ]* 11.5 Write property test for post-generation error Call ID inclusion
    - **Property 24: Post-Generation Error Call ID Inclusion**
    - **Validates: Requirements 6.5**
  
  - [ ]* 11.6 Write property test for validation error message quality
    - **Property 25: Validation Error Message Quality**
    - **Validates: Requirements 6.6**

- [x] 12. Implement main execute() method
  - [x] 12.1 Wire all components together in execute() method
    - Get credentials and parameters
    - Initialize output arrays for both outputs: [[], []]
    - Loop through input items independently
    - For each item: read audio → validate → generate call_id → submit → poll → enrich → flatten → route
    - Handle errors per item (don't let one failure stop others)
    - Return two-dimensional array with High Risk items at index 0, Normal items at index 1
    - _Requirements: 7.1, 7.2, 7.4, 9.1, 9.2, 9.3_
  
  - [ ]* 12.2 Write property test for independent item state isolation
    - **Property 26: Independent Item State Isolation**
    - **Validates: Requirements 7.1**
  
  - [ ]* 12.3 Write property test for no request batching
    - **Property 27: No Request Batching**
    - **Validates: Requirements 7.2**
  
  - [ ]* 12.4 Write property test for error isolation between items
    - **Property 28: Error Isolation Between Items**
    - **Validates: Requirements 7.4**
  
  - [ ]* 12.5 Write integration tests for complete end-to-end flow
    - Test complete flow with mocked API responses
    - Test high risk routing end-to-end
    - Test normal routing end-to-end
    - Test multiple items with mixed risk scores
    - _Requirements: 4.1, 4.2, 7.1, 7.4_

- [x] 13. Add node assets and metadata
  - Create voiceops.svg icon file
  - Create VoiceOpsAnalyzeCall.node.json with node metadata
  - Update package.json with n8n node registration
  - _Requirements: 9.4_

- [ ] 14. Final checkpoint - Comprehensive testing
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Create downstream compatibility verification
  - [ ]* 15.1 Write unit tests for Slack node compatibility
    - Verify flattened fields are accessible with dot notation
    - Test that risk_score, fraud_likelihood, explanation are directly referenceable
    - _Requirements: 10.1_
  
  - [ ]* 15.2 Write unit tests for Google Sheets node compatibility
    - Verify flattened fields can be mapped to columns
    - Test that all flattened fields use consistent naming
    - _Requirements: 10.2, 10.3_

- [ ] 16. Documentation and build verification
  - Create README.md with installation and usage instructions
  - Add JSDoc comments to all public functions
  - Build the node: npm run build
  - Test installation: npm link
  - Verify node appears in n8n UI
  - _Requirements: 8.10_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each property test should run minimum 100 iterations using fast-check
- All property tests must include the tag: `Feature: voiceops-analyze-call, Property {number}: {property_text}`
- Checkpoints ensure incremental validation and provide opportunities for user feedback
- The node must strictly route each item to exactly one output (mutual exclusivity)
- TypeScript strict mode must be enabled throughout
- No hardcoded values - all configuration through credentials and parameters
