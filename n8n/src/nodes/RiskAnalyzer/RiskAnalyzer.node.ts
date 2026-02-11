import {
	IExecuteFunctions,
	INodeExecutionData,
	INodeType,
	INodeTypeDescription,
	NodeOperationError,
} from 'n8n-workflow';

/**
 * VoiceOps Risk Analyzer Node
 *
 * Receives the JSON response from the HTTP Request node (which calls the
 * VoiceOps /api/v1/analyze-call endpoint) and routes items by risk score.
 *
 * - Reads `input_risk_assessment.risk_score` from the incoming JSON.
 * - Compares against a configurable Risk Threshold.
 * - Routes to output 0 (High Risk) or output 1 (Normal).
 */
export class RiskAnalyzer implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'VoiceOps Risk Analyzer',
		name: 'riskAnalyzer',
		icon: 'file:riskanalyzer.svg',
		group: ['transform'],
		version: 1,
		description: 'Routes VoiceOps analysis results by risk score — High Risk vs Normal',
		defaults: {
			name: 'Risk Analyzer',
		},
		inputs: ['main'],
		outputs: ['main', 'main'],
		outputNames: ['High Risk', 'Normal'],
		properties: [
			{
				displayName: 'Risk Threshold',
				name: 'riskThreshold',
				type: 'number',
				default: 65,
				typeOptions: {
					minValue: 0,
					maxValue: 100,
					numberPrecision: 0,
				},
				description:
					'Risk score threshold (0–100). Scores >= threshold route to High Risk output, scores < threshold route to Normal output.',
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const riskThreshold = this.getNodeParameter('riskThreshold', 0) as number;

		const highRiskOutput: INodeExecutionData[] = [];
		const normalOutput: INodeExecutionData[] = [];

		for (let i = 0; i < items.length; i++) {
			try {
				const json = items[i].json as Record<string, any>;

				// ── Extract risk_score from input_risk_assessment ──
				const riskAssessment = json.input_risk_assessment;
				if (!riskAssessment || typeof riskAssessment !== 'object') {
					throw new NodeOperationError(
						this.getNode(),
						'Missing "input_risk_assessment" object in input JSON',
						{ itemIndex: i },
					);
				}

				const riskScore: number =
					typeof riskAssessment.risk_score === 'number'
						? riskAssessment.risk_score
						: 0;

				const fraudLikelihood: string =
					riskAssessment.fraud_likelihood ?? 'unknown';

				// ── Route by threshold ──
				const isHighRisk = riskScore >= riskThreshold;

				const outputJson: Record<string, any> = {
					// Pass through the entire original payload
					...json,
					// Flatten useful fields to top level for downstream nodes
					risk_score: riskScore,
					fraud_likelihood: fraudLikelihood,
					// Routing metadata
					_voiceops_meta: {
						risk_threshold_used: riskThreshold,
						is_high_risk: isHighRisk,
						routed_to: isHighRisk ? 'high_risk' : 'normal',
						processed_at: new Date().toISOString(),
					},
				};

				const outputItem: INodeExecutionData = { json: outputJson };

				if (isHighRisk) {
					highRiskOutput.push(outputItem);
				} else {
					normalOutput.push(outputItem);
				}
			} catch (error: any) {
				if (this.continueOnFail()) {
					normalOutput.push({
						json: {
							error: error.message || 'Unknown error',
							itemIndex: i,
							timestamp: new Date().toISOString(),
						},
					});
				} else {
					if (error instanceof NodeOperationError) throw error;
					throw new NodeOperationError(this.getNode(), error.message, {
						itemIndex: i,
					});
				}
			}
		}

		// Output 0 = High Risk, Output 1 = Normal
		return [highRiskOutput, normalOutput];
	}
}
