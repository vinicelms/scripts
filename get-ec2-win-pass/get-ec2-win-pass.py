from rich.progress import BarColumn, Progress, TimeElapsedColumn, TimeRemainingColumn
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.style import Style
from rich.align import Align
from rich.live import Live
import click
import boto3
import os
import base64


console = Console(log_path=False)
rule = Rule(
    title="Start to collect Windows password from required key",
    characters="-",
    style="rule.line",
    end="\n",
    align="center",
)
progress = Progress(
    "[progress.description]{task.description}",
    BarColumn(),
    "[progress.percentage]{task.percentage:>3.0f}%",
    "•",
    "[progress.completed]{task.completed}",
    "|",
    "[progress.total]{task.total}",
    "•",
    TimeRemainingColumn(),
    "|",
    TimeElapsedColumn(),
    console=console,
)


class AWS:
    def __init__(
        self,
        access_key=None,
        secret_key=None,
        session_token=None,
        profile=None,
        region="us-east-1",
    ):
        self.__access_key = access_key
        self.__secret_key = secret_key
        self.__session_token = session_token
        self.__profile = profile
        self.__region = region
        console.log("Validating data to create session on AWS")
        if self.__profile:
            if self.__access_key and self.__secret_key and self.__session_token:
                console.log(
                    "Access Key, Secret Key and Session Token will be ignored. "
                    "The Profile Name precedence is more bigger."
                )
                pass

            console.log(
                f"Creating session on AWS with parameter Profile as [green]{self.__profile}[/green]"
            )
            self.__session = boto3.Session(
                profile_name=self.__profile, region_name=self.__region
            )
            console.log("Session created on AWS with success status")
        elif (
            not self.__access_key and not self.__secret_key and not self.__session_token
        ):
            console.log(
                "If Profile Name not be defined, Access Key, Secret Key and Session Token need to be defined"
            )
            raise EnvironmentError("Parameters defined incorrectly")
        else:
            console.log(
                "Creating session on AWS with Access Key, Secret Key and Session Token"
            )
            self.__session = boto3.Session(
                aws_access_key_id=self.__access_key,
                aws_secret_access_key=self.__secret_key,
                aws_session_token=self.__session_token,
                region_name=self.__region,
            )
            console.log("Session created on AWS with success status")

    def get_session(self):
        return self.__session


class Crypt:
    def __init__(self, pem_file):
        self.pem_file = pem_file
        self.pem_data = self.load_pem_file()

    def load_pem_file(self):
        with open(self.pem_file, "rb") as pem:
            return load_pem_private_key(pem.read(), password=None)

    def decrypt(self, data):
        return self.pem_data.decrypt(data, padding.PKCS1v15()).decode("utf-8")


@click.command()
@click.option(
    "--profile-name",
    envvar="AWS_PROFILE",
    help="Set AWS Profile Name",
    required=False,
)
@click.option(
    "--region-name",
    envvar="AWS_REGION",
    default="us-east-1",
    show_default=True,
    help="Set AWS Region Name",
    required=True,
)
@click.option(
    "--access-key",
    envvar="AWS_ACCESS_KEY_ID",
    help="Set AWS Access Key ID",
    required=False,
)
@click.option(
    "--secret-key",
    envvar="AWS_SECRET_ACCESS_KEY",
    help="Set AWS Session Token",
    required=False,
)
@click.option(
    "--session-token",
    envvar="AWS_SESSION_TOKEN",
    help="Set AWS Session Token",
    required=False,
)
@click.option("--pem-file", help="Set PEM file location", required=True)
@click.option(
    "--instance-id",
    help="Set Instance ID to get password",
    required=False,
    multiple=True,
)
def main(
    profile_name,
    region_name,
    access_key,
    secret_key,
    session_token,
    pem_file,
    instance_id,
):
    aws_session = AWS(
        profile=profile_name,
        region=region_name,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    ).get_session()
    if os.path.exists(pem_file) and os.path.isfile(pem_file):
        file_name = os.path.basename(pem_file)
        console.log(f"PEM file: {pem_file}")
        console.log(f"Loading PEM file")
        pem = Crypt(pem_file=pem_file)
    client = aws_session.client("ec2")
    if instance_id:
        console.log(f"Get EC2 instances by tag: {list(instance_id)}")
        try:
            instance_list = client.describe_instances(InstanceIds=list(instance_id))
            console.log(instance_list)
        except client.exceptions.ClientError as exc:
            console.log(exc)
            exit(0)

    else:
        console.log(
            f"List EC2 instances with Key Pair: [magenta]{file_name.split(".")[0]}[/magenta]"
        )
        client = aws_session.client("ec2")
        instance_list = client.describe_instances(
            Filters=[{"Name": "key-name", "Values": [file_name.split(".")[0]]}]
        )
    with progress:
        windows_instances = []
        instance_data = []
        for reservation in instance_list["Reservations"]:
            for instance in reservation["Instances"]:
                if instance["Platform"] == "windows":
                    if instance["State"]["Name"] == "running":
                        windows_instances.append(instance)
                    else:
                        console.log(
                            f"Instance [magenta]{instance["InstanceId"]}[/magenta] isn't [magenta]Running[/magenta]. [bold red]This instance will be ignored.[/bold red]"
                        )
        if len(windows_instances) > 0:
            instances_progress = progress.add_task(
                "Collecting Instances password", total=len(windows_instances)
            )

            for instance in windows_instances:
                info = client.get_password_data(InstanceId=instance["InstanceId"])
                data = {
                    "instance_id": instance["InstanceId"],
                    "instance_name": [
                        tag["Value"] for tag in instance["Tags"] if tag["Key"] == "Name"
                    ][0],
                    "instance_user": "Administrator",
                    "instance_pass": pem.decrypt(base64.b64decode(info["PasswordData"])),
                }
                progress.update(instances_progress, advance=1)
                instance_data.append(data)
            instance_data = sorted(instance_data, key=lambda x: x["instance_name"])
        else:
            console.log("Required instances isn't running Windows")

    if len(windows_instances) > 0:
        table = Table(
            show_header=True,
            header_style="bold green",
            show_footer=False,
            title="Windows Instances Password Data",
        )
        table_centered = Align.left(table)

        with Live(table_centered, console=console, screen=False, refresh_per_second=20):
            table.add_column("Instance ID", justify="center")
            table.add_column("Name", justify="left")
            table.add_column("User", justify="left")
            table.add_column("Password", justify="left")
            table.row_styles = [
                Style(bgcolor="gray74", color="black"),
                Style(bgcolor="gray82", color="black"),
            ]
            for item in instance_data:
                table.add_row(
                    item["instance_id"],
                    item["instance_name"],
                    item["instance_user"],
                    item["instance_pass"],
                )

    console.log("[green]Finish![/green]")


if __name__ == "__main__":
    main()
