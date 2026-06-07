# Arkos2Basic

Converts Arkos Tracker 3 text exports to CVBasic MUSIC blocks. Handles note transposition, variable note duration, percussion detection and intro/loop splitting. Targets ColecoVision, MSX and Sega SG-1000.

## Installation

```
pipx install arkos2basic
```

### What if you don’t have pipx installed?

Depending on your OS, you can install pipx with this command:

#### MacOS

```
brew install pipx
```

#### Linux

```
sudo apt install pipx
```
  
## Usage

Export your song from Arkos Tracker as a TXT file, then launch this command:

```
arkos2basic <input-file> <output-file>
```

If your song has a loop, the app will provide you with two files:

- `<output-file-path>/<output-file-stem>.bas`
- `<output-file-path>/<output-file-stem>_loop.bas`

## Example

Let's imagine you have a TXT source file named `mymusic.txt` in the same folder of your CVBasic project.

Convert the source file with the command:

```
arkos2basic mymusic.txt mymusic.bas
```

If the song has a loop, arkos2basic will provide you these two files:

```
mymusic.bas
mymusic_loop.bas
```

To test if the music has been properly converted, create a `test_music.bas` file with this code:

```basic 
DIM loop_on
loop_on = 0
PLAY FULL
PLAY mymusic
DO
    WAIT
    IF MUSIC.PLAYING = 0 AND loop_on = 0 THEN
        loop_on = 1
        PLAY mymusic_loop
    END IF
LOOP WHILE 1

INCLUDE mymusic.bas
INCLUDE mymusic_loop.bas
```

## Requirements

Python 3.12 or better.
