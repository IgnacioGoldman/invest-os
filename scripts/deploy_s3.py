"""Create/update the repository's S3 CloudFormation stack using an AWS CLI session."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--stack", default="invest-os-data")
    parser.add_argument("--repository", default="IgnacioGoldman/invest-os")
    parser.add_argument("--configure-github", action="store_true")
    args = parser.parse_args()
    aws = ["aws", "--region", args.region, "--no-cli-pager", "--output", "json"]
    if args.profile:
        aws += ["--profile", args.profile]

    def call(*arguments):
        return json.loads(subprocess.check_output(aws + list(arguments), text=True))

    existing = subprocess.run(aws + ["cloudformation", "describe-stacks", "--stack-name", args.stack],
                              capture_output=True, text=True)
    if existing.returncode == 0:
        stack = json.loads(existing.stdout)["Stacks"][0]
        provider = next(p["ParameterValue"] for p in stack["Parameters"] if p["ParameterKey"] == "ExistingGitHubProviderArn")
    elif "does not exist" in existing.stderr:
        providers = call("iam", "list-open-id-connect-providers")["OpenIDConnectProviderList"]
        provider = next((p["Arn"] for p in providers if p["Arn"].endswith("/token.actions.githubusercontent.com")), "")
    else:
        raise RuntimeError(existing.stderr.strip())

    subprocess.run(aws + [
        "cloudformation", "deploy", "--stack-name", args.stack,
        "--template-file", str(ROOT / "infrastructure/storage.json"),
        "--capabilities", "CAPABILITY_NAMED_IAM", "--no-fail-on-empty-changeset",
        "--parameter-overrides", f"GitHubRepository={args.repository}", f"ExistingGitHubProviderArn={provider}",
        "--tags", "Project=invest-os",
    ], check=True)
    outputs = {o["OutputKey"]: o["OutputValue"] for o in call("cloudformation", "describe-stacks", "--stack-name", args.stack)["Stacks"][0]["Outputs"]}
    config = {"bucket": outputs["DatabaseBucketName"], "region": outputs["Region"],
              "data_role_arn": outputs["DataRoleArn"], "infrastructure_role_arn": outputs["InfrastructureRoleArn"],
              "stack": args.stack}
    (ROOT / "infrastructure/storage-config.json").write_text(json.dumps(config, indent=2) + "\n")
    if args.configure_github:
        variables = {"INVEST_OS_DATA_BUCKET": config["bucket"], "AWS_REGION": config["region"],
                     "AWS_DATA_ROLE_ARN": config["data_role_arn"], "AWS_INFRA_ROLE_ARN": config["infrastructure_role_arn"],
                     "AWS_STORAGE_STACK": args.stack}
        for name, value in variables.items():
            subprocess.run(["gh", "variable", "set", name, "--repo", args.repository, "--body", value], check=True)
    print(json.dumps(config, indent=2))


if __name__ == "__main__":
    main()
