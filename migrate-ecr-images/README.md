# Migrate ECR Images

This project is to supporte migration ECR images from one account to another and allow you to get information of your ECR repositories.

## Example

```shell
> python main.py --profile-name my-profile --region us-east-1
[18:03:00] Validating data to create session on AWS
           Creating session on AWS with parameter Profile          
           Session created on AWS with success status
           List repositories on origin account
           Listing ECR repositories
           List all ECR repositories without Next Token
[18:03:02] Filtering repositories...
           ECR repositories founded (based on filter strategy): 5

                             ECR Repositories List
                    ┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓                                         
                    ┃ Repository Name ┃ Image Quantity ┃ Image Size ┃
                    ┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
                    │      repo_a     │       1        │  407.4MB   │
                    │      repo_b     │       1        │  125.3MB   │
                    │      repo_c     │       1        │  139.2MB   │
                    │      repo_d     │       1        │  474.5MB   │
                    │      repo_e     │       19       │   9.3GB    │
                    │      repo_f     │       23       │   10.4GB   │
                    └─────────────────┴────────────────┴────────────┘
```