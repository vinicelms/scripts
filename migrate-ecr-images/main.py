import boto3
import json
import os
import re
import click
from rich.progress import (
    BarColumn,
    Progress,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.style import Style
from rich.live import Live
from rich.align import Align
import concurrent.futures
from collections import namedtuple

console = Console(log_path=False)


class AWS:
    def __init__(
        self,
        access_key=None,
        secret_key=None,
        profile=None,
        region="us-east-1",
    ):
        self.__access_key = access_key
        self.__secret_key = secret_key
        self.__profile = profile
        self.__region = region
        console.log("Validating data to create session on AWS")
        if self.__profile:
            if self.__access_key and self.__secret_key:
                console.log(
                    "Access Key and Secret Key will be ignored. "
                    "The Profile Name has greater precedence"
                )
            console.log("Creating session on AWS with parameter Profile")
            self.__session = boto3.Session(
                profile_name=self.__profile, region_name=self.__region
            )
            console.log("Session created on AWS with success status")
        elif not self.__access_key and not self.__secret_key:
            console.log(
                "If Profile Name isn't defined, Access Key and Secret Key need to be defined"
            )
            raise EnvironmentError("Parameter defined incorrectly")
        else:
            console.log(
                "Creating session on AWS with Access Key, Secret Key and Session Token"
            )
            self.__session = boto3.Session(
                aws_access_key_id=self.__access_key,
                aws_secret_access_key=self.__secret_key,
            )
            console.log("Session created on AWS with success status")

    def get_session(self):
        return self.__session


class ECRRepo:
    def __init__(self, aws_session):
        self.__session = aws_session

    def list_repositories(self, filter_type=None, filter=None):
        client = self.__session.client("ecr")
        next_token = None
        flag_run = True
        repo_list_filtered = []
        console.log("Listing ECR repositories")
        while flag_run:
            if filter_type == "common":
                if not next_token:
                    console.log(
                        "List repositories without Next Token with Common strategy"
                    )
                    repo_list = client.describe_repositories(repositoryNames=filter)
                else:
                    console.log(
                        "List repositories with Next Token with Common strategy"
                    )
                    repo_list = client.describe_repositories(
                        repositoryNames=filter, nextToken=next_token
                    )
            else:
                if not next_token:
                    console.log("List all ECR repositories without Next Token")
                    repo_list = client.describe_repositories()
                else:
                    console.log("List all ECR repositories with Next Token")
                    repo_list = client.describe_repositories(nextToken=next_token)
            console.log("Filtering repositories...")
            for repo in repo_list["repositories"]:
                if filter_type == "regex":
                    if re.search(filter, repo["repositoryName"]):
                        repo_list_filtered.append(repo["repositoryName"])
                elif filter_type == "common-not":
                    if repo["repositoryName"] not in filter:
                        repo_list_filtered.append(repo["repositoryName"])
                elif filter_type == "regex-not":
                    if not re.search(filter, repo["repositoryName"]):
                        repo_list_filtered.append(repo["repositoryName"])
                else:
                    repo_list_filtered.append(repo["repositoryName"])
            if "nextToken" in repo_list:
                next_token = repo_list["nextToken"]
            else:
                flag_run = False

        console.log(
            f"ECR repositories founded (based on filter strategy): {len(repo_list_filtered)}"
        )
        return repo_list_filtered

    def list_images(self, repository_name):
        client = self.__session.client("ecr")
        next_token = None
        flag_run = True
        image_list = []
        console.log(f"Describe images from ECR repository: {repository_name}")
        while flag_run:
            if not next_token:
                img_list = client.describe_images(
                    repositoryName=repository_name, filter={"tagStatus": "TAGGED"}
                )
            else:
                img_list = client.describe_images(
                    repositoryName=repository_name,
                    filter={"tagStatus": "TAGGED"},
                    nextToken=next_token,
                )

            for image in img_list["imageIds"]:
                img = ECRImage(
                    digest=image["imageDigest"],
                    tag=image["imageTags"],
                    pushed_at=image["imagePushedAt"],
                )
                image_list.append(img)

            if "nextToken" in img_list:
                next_token = img_list["nextToken"]
            else:
                flag_run = False

        console.log(f"ECR repository images founded: {len(image_list)}")


class ECRImage:

    def __init__(self, digest, tags, pushed_at):
        self.digest = digest
        self.image_tags = tags
        self.pushed_at = pushed_at


@click.command()
@click.option(
    "--profile-name",
    envvar="AWS_PROFILE",
    help="Set origin AWS Profile Name",
    required=False,
)
@click.option(
    "--region",
    envvar="AWS_REGION",
    default="us-east-1",
    show_default=True,
    help="Set origin AWS Region Name",
    required=True,
)
@click.option(
    "--access-key",
    envvar="AWS_ACCESS_KEY_ID",
    help="Set origin AWS Access Key ID",
    required=False,
)
@click.option(
    "--secret-key",
    envvar="AWS_SECRET_ACCESS_KEY",
    help="Set origin AWS Secret Access Key",
    required=False,
)
@click.option(
    "--dest-profile-name", help="Set destiny AWS Profile Name", required=False
)
@click.option("--dest-region", help="Set destiny AWS Region Name", required=False)
@click.option("--dest-access-key", help="Set destiny AWS Access Key", required=False)
@click.option("--dest-secret-key", help="Set destiny AWS Secret Key", required=False)
@click.option(
    "--repo", help="Set ECR Repository name to filter", required=False, multiple=True
)
@click.option(
    "--repo-regex", help="Set regex to filter ECR Repositories", required=False
)
@click.option(
    "--not-repo",
    help="Set ECR Repository name to not use",
    required=False,
    multiple=True,
)
@click.option(
    "--not-repo-regex", help="Set regex to not use ECR Repositories", required=False
)
@click.option(
    "--threads",
    help="Threads quantity to process data",
    default=50,
    show_default=True,
    required=True,
    type=int,
)
def migrate(
    profile_name,
    region,
    access_key,
    secret_key,
    dest_profile_name,
    dest_region,
    dest_access_key,
    dest_secret_key,
    repo,
    not_repo,
    repo_regex,
    not_repo_regex,
    threads,
):
    """
    This script is to list and migrate all repositories, if you don't want to filter repo

    Pay attention to use AWS account origin and destiny
    """
    repo_control = sum(1 for var in [repo, not_repo, repo_regex, not_repo_regex] if var)
    if repo_control > 1:
        raise EnvironmentError(
            "This options can't be defined together: Repo, Not-Repo, Repo-Regex, Not-Repo-Regex. Only one can be defined!"
        )
    aws_session = AWS(
        profile=profile_name,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
    ).get_session()
    # dest_aws_session = AWS(
    #     profile=dest_profile_name,
    #     region=dest_region,
    #     access_key=dest_access_key,
    #     secret_key=dest_secret_key,
    # ).get_session()
    console.log("List repositories on origin account")
    ecr = ECRRepo(aws_session=aws_session)
    if repo:
        repo_list = ecr.list_repositories(filter_type="common", filter=list(repo))
    elif not_repo:
        repo_list = ecr.list_repositories(
            filter_type="common-not", filter=list(not_repo)
        )
    elif repo_regex:
        repo_list = ecr.list_repositories(filter_type="regex", filter=repo_regex)
    elif not_repo_regex:
        repo_list = ecr.list_repositories(
            filter_type="regex-not", filter=not_repo_regex
        )
    else:
        repo_list = ecr.list_repositories()


if __name__ == "__main__":
    migrate()
