/**
 * TypeScript interfaces for VoiceOps Analyze Call Node
 *
 * The node receives JSON from the HTTP Request node and routes by risk score.
 */

/**
 * The JSON payload the node expects from the upstream HTTP Request node.
 * Matches the response structure of the VoiceOps /api/v1/analyze-call endpoint.
 */
export interface IVoiceOpsInput {
	call_id: string;
	call_timestamp: string;
	input_risk_assessment: {
		risk_score: number;
		fraud_likelihood: 'low' | 'medium' | 'high';
		confidence: number;
	};
	rag_output: {
		grounded_assessment: string;
		explanation: string;
		recommended_action: string;
		confidence: number;
		regulatory_flags: string[];
		matched_patterns: string[];
	};
	backboard_thread_id: string;
}
