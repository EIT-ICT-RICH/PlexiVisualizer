# Network visualizer for the RiSCH plexi scheduler
to be used with the StreamingInterface of the plexi scheduler

### Dependencies:
Python 3.x

## Usage:
### options
--ip <ip which the server will bind to> default is localhost
### preparations
a folder named "logs"and "snapshots" is needed in the root directory  
Furthermore the userdatabase is saved in "users.txt" in the format:
name$password$csvformat of allowed schedulers
### gui usage
after starting a user can browse to <ip> to view the gui. The gui uses websockets, this is supported in all modern browsers as well as the latest mobile browsers