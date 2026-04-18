import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";
import { AppConfig } from "./utils/config-manager";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as path from "path";

export interface ExtractionStackProps extends cdk.NestedStackProps {
  config: AppConfig;
  insightsBucket: s3.IBucket; // Phase 2で作成したS3バケット
}

/**
 * Phase 3: 日記抽出スタック
 *
 * GitHub Webhook + Lambdaで日記をリアルタイム抽出し、S3のdraft/に保存する
 */
export class ExtractionStack extends cdk.NestedStack {
  public readonly webhookUrl: string;
  constructor(scope: Construct, id: string, props: ExtractionStackProps) {
    super(scope, id, props);

    const { config, insightsBucket } = props;

    // GitHub設定の確認
    const githubConfig = (config as any).github;
    if (!githubConfig) {
      throw new Error("config.yamlにgithub設定が必要です");
    }

    const githubOwner = githubConfig.owner;
    const githubRepo = githubConfig.repo;

    if (!githubOwner || !githubRepo) {
      throw new Error("config.yamlにgithub.ownerとgithub.repoが必要です");
    }

    // Lambda: 日記抽出（Webhook対応）
    const extractionLambda = new PythonFunction(this, "DiaryExtractionLambda", {
      runtime: lambda.Runtime.PYTHON_3_13,
      entry: path.join(__dirname, "../../batch/extract_diary"),
      index: "lambda_function.py",
      handler: "handler",
      timeout: cdk.Duration.minutes(15), // LLM呼び出しがあるため長め
      memorySize: 512,
      environment: {
        GITHUB_TOKEN_SECRET_NAME: `${config.stack_name_base}/github-token`,
        GITHUB_WEBHOOK_SECRET_NAME: `${config.stack_name_base}/github-webhook-secret`,
        GITHUB_OWNER: githubOwner,
        GITHUB_REPO: githubRepo,
        S3_BUCKET_NAME: insightsBucket.bucketName,
      },
      logGroup: new logs.LogGroup(this, "DiaryExtractionLambdaLogGroup", {
        logGroupName: `/aws/lambda/${config.stack_name_base}-diary-extraction`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }),
    });

    // IAM権限: S3（draft/への書き込み、draft/の読み取り）
    insightsBucket.grantWrite(extractionLambda, "draft/*");
    insightsBucket.grantRead(extractionLambda, "draft/*");

    // IAM権限: Secrets Manager（GitHub Token + Webhook Secret読み取り）
    extractionLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [
          `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${config.stack_name_base}/github-token-*`,
          `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${config.stack_name_base}/github-webhook-secret-*`,
        ],
      })
    );

    // IAM権限: Bedrock（LLM呼び出し - Claude Haiku 4.5）
    // Geographic CRIS: inference profileと全destination regionsへのアクセスが必要
    extractionLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock:InvokeModel"],
        resources: [
          // Inference Profile (source region: 東京)
          `arn:aws:bedrock:ap-northeast-1:${this.account}:inference-profile/jp.anthropic.claude-haiku-4-5-20251001-v1:0`,
          // Foundation Models (destination regions: 東京・大阪)
          `arn:aws:bedrock:ap-northeast-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0`,
          `arn:aws:bedrock:ap-northeast-3::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0`,
        ],
      })
    );

    // API Gateway: GitHub Webhook エンドポイント
    const api = new apigateway.RestApi(this, "WebhookApi", {
      restApiName: `${config.stack_name_base}-webhook-api`,
      description: "GitHub Webhook receiver for diary extraction",
      deployOptions: {
        stageName: "prod",
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        metricsEnabled: true,
      },
    });

    // POST /webhook/github-diary
    const webhookResource = api.root
      .addResource("webhook")
      .addResource("github-diary");

    webhookResource.addMethod(
      "POST",
      new apigateway.LambdaIntegration(extractionLambda, {
        proxy: true, // API Gateway から Lambda へのリクエストをそのまま渡す
      }),
      {
        authorizationType: apigateway.AuthorizationType.NONE, // Lambda内で署名検証
      }
    );

    // Webhook URL を保存
    this.webhookUrl = `${api.url}webhook/github-diary`;

    // CloudFormation Outputs
    new cdk.CfnOutput(this, "ExtractionLambdaArn", {
      value: extractionLambda.functionArn,
      description: "ARN of the diary extraction Lambda function",
      exportName: `${config.stack_name_base}-extraction-lambda-arn`,
    });

    new cdk.CfnOutput(this, "WebhookUrl", {
      value: this.webhookUrl,
      description: "GitHub Webhook URL - Configure this in GitHub repository settings",
      exportName: `${config.stack_name_base}-webhook-url`,
    });

    new cdk.CfnOutput(this, "WebhookApiId", {
      value: api.restApiId,
      description: "Webhook API Gateway ID",
      exportName: `${config.stack_name_base}-webhook-api-id`,
    });
  }
}