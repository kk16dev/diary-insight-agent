import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
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
 * Phase 3: 日記抽出バッチスタック
 *
 * EventBridge + Lambdaで日記を自動抽出し、S3のdraft/に保存する
 */
export class ExtractionStack extends cdk.NestedStack {
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

    // Lambda: 抽出バッチ
    const extractionLambda = new PythonFunction(this, "DiaryExtractionLambda", {
      runtime: lambda.Runtime.PYTHON_3_13,
      entry: path.join(__dirname, "../../batch/extract_diary"),
      index: "lambda_function.py",
      handler: "handler",
      timeout: cdk.Duration.minutes(15), // LLM呼び出しがあるため長め
      memorySize: 512,
      environment: {
        GITHUB_TOKEN_SECRET_NAME: `${config.stack_name_base}/github-token`,
        GITHUB_OWNER: githubOwner,
        GITHUB_REPO: githubRepo,
        S3_BUCKET_NAME: insightsBucket.bucketName,
        LOOKBACK_DAYS: "7", // 過去7日分を遡る
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

    // IAM権限: Secrets Manager（GitHub Token読み取り）
    extractionLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [
          `arn:aws:secretsmanager:${this.region}:${this.account}:secret:${config.stack_name_base}/github-token-*`,
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

    // EventBridge Scheduler: 毎日 2:00 JST（UTC 17:00）
    const extractionSchedule = new events.Rule(this, "DiaryExtractionSchedule", {
      schedule: events.Schedule.cron({
        minute: "0",
        hour: "17", // UTC 17:00 = JST 2:00
        day: "*",
        month: "*",
        year: "*",
      }),
      description: "Daily diary extraction batch (2:00 JST)",
    });

    // EventBridge → Lambda
    extractionSchedule.addTarget(new targets.LambdaFunction(extractionLambda));

    // CloudFormation Outputs
    new cdk.CfnOutput(this, "ExtractionLambdaArn", {
      value: extractionLambda.functionArn,
      description: "ARN of the diary extraction Lambda function",
      exportName: `${config.stack_name_base}-extraction-lambda-arn`,
    });

    new cdk.CfnOutput(this, "ExtractionScheduleArn", {
      value: extractionSchedule.ruleArn,
      description: "ARN of the EventBridge schedule rule",
      exportName: `${config.stack_name_base}-extraction-schedule-arn`,
    });
  }
}