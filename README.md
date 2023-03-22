# DCA trading bot python script

### dca_bot_init.py

This creates a job to run swap. This needs to run only once at the very beginning.

### dca_bot_execute.py

This reads data from `triggerable_deposit()` function from DCA bot vyper smart contract. If it doesn't return `0,0,0`, execute a job with the data. And put logs with swap id and remaining trade number to prevent repeating the same job execution.

### run.sh

This is a simple shell script to run dca_bot_execute.py. We can register it on crontab so that the system runs it every minute.