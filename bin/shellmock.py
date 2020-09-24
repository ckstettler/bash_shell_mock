#!/usr/bin/python
import argparse
import os
import json
import re
import shlex

BATS_TEST_DIRNAME=os.getenv('BATS_TEST_DIRNAME',".")
TEMP_STUBS_DIR=BATS_TEST_DIRNAME+'/tmpstubs'

DEBUG_ON=False

def debug(msg):
    """
    Writes output to a debug log. If the code is in debug mode.
    """
    print("debug: {}".format(msg))

def normalize_args(argstr):
    """
    Convert an array from argument to a single string placing
    double quotes around any that contain spaces.
    """
    debug ("normalize_args: *{}*".format(argstr))

    parts = shlex.split(argstr)

    retstr=""
    for p in parts:
       if " " in p.strip():
           debug("normalize_args: found space *{}*".format(p.strip()))
           retstr = retstr + ' "' +p.strip() + '"'
       else:
           retstr = retstr + ' ' + p.strip()


    retstr = retstr.strip()
    debug("normalize_args: normalized string *{}*".format(retstr))

    return retstr

def save_capture_record(record):
    """
    Record the details about the item being stubbed.
    """

    data = load_capture_records(record['command'])
    data.append(record)

    filen = TEMP_STUBS_DIR + "/" + record['command'] +".playback.capture.tmp"
    debug("save_capture_record: Saving capture record {} to {}".format(record, filen))

    with open(filen, "w") as outfile:
        json.dump(data, outfile, indent=4, sort_keys=True)

def save_state_record(record):
    """
    The state file keeps track of which result to replay when there are duplicate expectations.
    """

    data = load_state_records(record['command'])

    found = False
    for s in data:
      if (s['command']==record['command'] and
          s['match_args']==record['match_args'] and
          s['match_stdin']==record['match_stdin']):
          s['next_idx']=record['next_idx']
          found = True
          debug("save_state_record: found match updating state : {}".format(s))

    if (not found):
      data.append(record)

    filen = TEMP_STUBS_DIR + "/" + record['command'] +".playback.state.tmp"
    debug("save_state_record: Saving state record {} to {}".format(record, filen))
    with open(filen, "w") as outfile:
        json.dump(data, outfile, indent=4, sort_keys=True)

def load_state_records(command):
    """
    Loads all of the state records into one array for ease of filtering.
    """
    filen = TEMP_STUBS_DIR + "/" + command +".playback.state.tmp"
    debug("load_state_records: Loading state records from {}".format(filen))

    if (not os.path.exists(filen)):
        return []

    with open(filen, "r") as infile:
        data = json.load(infile)

    return data

def lookup_state_record(command, args, stdin):
    """
    Maintain which record of the available mocks was last used.  The primary
    key into the record is the command+args+stdin
    """

    debug("lookup_state_record: cmd:{} args:{} stdin:{}".format(command, args, stdin))
    data = load_state_records(command)
    for s in data:
        if (s['command']==command and
            s['match_args']==args and
            s['match_stdin']==stdin):
            debug("lookup_state_record: matched: {}".format(s))
            return s

    s = { 'command': command,
          'match_args': args,
          'match_stdin' : stdin,
          'next_idx' : 0
        }
    debug("lookup_state_record: matched: {}".format(s))
    return s
def load_capture_records(command):
    """
    Loads all of the capture records which is a list of mocked values into one array for ease of filtering.
    """
    filen = TEMP_STUBS_DIR + "/" + command +".playback.capture.tmp"
    debug("load_capture_records: Loading state records from {}".format(filen))

    if (not os.path.exists(filen)):
        return []

    with open(filen, "r") as infile:
        data = json.load(infile)

    return data

def is_exact_match(actual, stubvalue):
    """
    This fuction checks to see if there is an exact match
    of the actual and stubdef.
    """
    return actual.strip() == stubvalue.strip()

def is_partial_match(actual, stubvalue):
    """
    This function checks to see if the actual string starts with the
    stubvalue.
    """
    return actual.startswith(stubvalue)

def is_regex_match(actual, stubvalue):
    """
    This function compares the actual input to the regex recorded for the stub.
    """
    return re.match(stubvalue, actual)

def does_match_stub(command, args, stdin, stubdef):
    """
    This function takes the stub definition and checks to see if the
    command, args and stdin are a match to it.
    """
    match = False
    if (stubdef['args_match_type'] == 'exact'):
        match = is_exact_match(args, stubdef['match_args'])
    elif (stubdef['args_match_type'] == 'partial'):
        match = is_partial_match(args, stubdef['match_args'])
    elif (stubdef['args_match_type'] == 'regex'):
        match = is_regex_match(args, stubdef['match_args'])

    #Short circuit
    if (not match):
        return False

    if (stubdef['stdin_match_type'] == 'exact'):
        match = is_exact_match(stdin, stubdef['match_stdin'])
    elif (stubdef['stdin_match_type'] == 'partial'):
        match = is_partial_match(stdin, stubdef['match_stdin'])
    elif (stubdef['stdin_match_type'] == 'regex'):
        match = is_regex_match(stdin, stubdef['match_stdin'])

    debug("does_match_stub: match:{} args:{} stdin:{} stubdef:{}".format(match, args, stdin, stubdef))
    return match

def lookup_stub_matches(command, args, stdin):
    """
    This function looks up the state record that matches the given command
    args and stdin and return it.
    """

    matches = list()
    mocks = load_capture_records(command)
    for m in mocks:
        if (does_match_stub(command, args, stdin, m)):
            matches.append(m)

    return matches

def add_expect():
    """
    Creates the stub file and updates the data files that maintain the state
    and the stub details.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="command", action="store")
    parser.add_argument("-S", "--source", dest="source_script", required=False, help="Source the provided script when matched.", action="store")
    parser.add_argument("-e", "--exec", dest="exec_script", required=False, help="Execute the provided script when matched.", action="store")
    parser.add_argument("-t", "--args-match-type", dest="args_match_type", required=False, help="partial, exact, or regex for argument list matching.", action="store")
    parser.add_argument("-T", "--stdin-match-type", dest="stdin_match_type", required=False, help="partial, exact, or regex for stdin input matching.", action="store")
    parser.add_argument("-m", "--match-args", dest="match_args", required=False, help="argument list to use in matching.", action="store")
    parser.add_argument("-M", "--match-stdin", dest="match_stdin", required=False, help="stdin to use in matching.", action="store")
    parser.add_argument("-s", "--status", dest="status", required=False, help="Status to return from the mock script.", action="store", type=int)
    parser.add_argument("-o", "--output", dest="output", required=False, help="Simulated output to return.", action="store")
    args = parser.parse_args()

    print(args.source_script)
    print(args.exec_script)
    print(args.args_match_type)
    print(args.command)

    cmd = TEMP_STUBS_DIR + "/" + args.command

    debug("shellmock_expect: FORWARD={}".format(args.exec_script))
    debug("shellmock_expect: MATCH={}".format(args.match_args))
    debug("shellmock_expect: OUTPUT={}".format(args.output))
    debug("shellmock_expect: STATUS={}".format(args.status))
    debug("shellmock_expect: MTYPE={}".format(args.args_match_type))
    debug("shellmock_expect: MATCH_IN={}".format(args.match_stdin))
    debug("shellmock_expect: IN_MTYPE={}".format(args.stdin_match_type))

    #-----------------------------------------------------------
    # If the command has not been stubbed then generate the stub
    #-----------------------------------------------------------
    if not os.path.exists(TEMP_STUBS_DIR):
        debug("shellmock_expect: creating stub dir {}".format(TEMP_STUBS_DIR))
        os.makedirs(TEMP_STUBS_DIR, 0755)

    with open(cmd,"w+") as stub:
        stub.write("#!/usr/bin/env bash\n")

    # Determine the type of stub.  If an alternative script should be executed
    # or if the script should be sourced or the normnal scenario of replaying
    # output or a particular status.
    if args.exec_script != '':
        stub_type = "FORWARD"
    elif args.source_script != '':
        stub_type = "SOURCE"
    else:
        stub_type = "NORMAL"


    capture_record = { 'match_args': normalize_args(args.match_args),
                         'command': args.command,
                         'stub_type': stub_type,
                         'exec_script': args.exec_script,
                         'status': args.status,
                         'args_match_type': args.args_match_type,
                         'stdin_match_type': args.stdin_match_type,
                         'match_stdin': normalize_args(args.match_stdin),
                         'output' : args.output
                      }
    debug ("shellmock_expect: normalized arg match string {}".format(capture_record))
    save_capture_record(capture_record)


def mock_replay(command, args, stdin):
    """
    This function processes and execute the mock that was requested.

    The primary key into the playback files is the command, the input arguments, and
    any stdin values.
    """

    args = normalize_args(args)
    stdin = normalize_args(stdin)

    debug("shellmock_replay: cmd: {} match: *{}* in_match: *{}*".format(command, args, stdin))


    matches = lookup_stub_matches(command, args, stdin)
    if (len(matches)==0):
        return 99

    debug("shellmock_replay: cmd: {} match count: {}".format(command, len(matches)))

    state_record = lookup_state_record(command, args, stdin)

    # Adjust the index if we have wrapped.
    idx = state_record['next_idx']
    if (idx >= len(matches)):
        idx = 0

    match = matches[idx]
    debug("shellmock_replay: match:{}".format(match))

    # Maintain the state for this set matching criteria
    state_record['next_idx']=idx+1
    save_state_record(state_record)

    if (match['stub_type'] == 'FORWARD'):
        debug("shellmock_replay: action: forward: {}".format(match['exec_script']))
        print('SCRIPT|{}'.format(match['exec_script']))
        return 98
    elif (match['stub_type'] == 'SOURCE'):
        debug("shellmock_replay: action: source: {}".format(match['exec_script']))
        print('SOURCE|{}'.format(match['exec_script']))
        return 97
    elif (match['stub_type'] == 'NORMAL'):
        if (match['output'] is not None):
            print("{}\n".format(match['output']))

        if (match['status'] is not None):
            retstat = int(match['status'])
        else:
            retstat = 0

        debug("shellmock_replay: action: normal: status:{} output: {}".format(retstat, match['output']))
        return retstat

    return 99
#
#
#    local rec
#    typeset -i rec
#
#    local count
#    typeset -i count
#
#    #-------------------------------------------------------------------------------------
#    # Get the record index.  If there are multiple matches then they are returned in order
#    #-------------------------------------------------------------------------------------
#    rec=$(mock_state_match "$match" "$in_match")
#    if [ "$rec" = "0" ]; then
#        shellmock_capture_err "No record match found stdin:*$in_match* cmd:$cmd args:*$match*"
#        return 99
#    fi
#
#    shellmock_debug "shellmock_replay: matched rec: $rec"
#    count=$(mock_capture_match "$match" "$in_match"| $WC -l)
#    entry=$(mock_capture_match "$match" "$in_match"| $HEAD -${rec} | $TAIL -1)
#
#    shellmock_debug "shellmock_replay: count: $count entry: $entry"
#    #-------------------------------
#    # If no entry is found then fail
#    #-------------------------------
#    if [ -z "$entry" ]; then
#        shellmock_capture_err "No match found for stdin: *$in_match* cmd: *$cmd* - args: *$match*"
#        exit 99
#    fi
#
#    local action=$($ECHO "$entry" | $AWK 'BEGIN{FS="@@"}{print $2}')
#    local output=$($ECHO "$entry" | $AWK 'BEGIN{FS="@@"}{print $3}')
#    local status=$($ECHO "$entry" | $AWK 'BEGIN{FS="@@"}{print $4}')
#    local mtype=$($ECHO "$entry" | $AWK 'BEGIN{FS="@@"}{print $5}')
#    local in_mtype=$($ECHO "$entry" | $AWK 'BEGIN{FS="@@"}{print $6}')
#
#    shellmock_debug "shellmock_replay: action: $action"
#    shellmock_debug "shellmock_replay: output: $output"
#    shellmock_debug "shellmock_replay: status: $status"
#    shellmock_debug "shellmock_replay: mtype: $mtype"
#    shellmock_debug "shellmock_replay: in_mtype: $in_mtype"
#
#    #--------------------------------------------------------------------------------------
#    # If there are multiple responses for a given match then keep track of a response index
#    #--------------------------------------------------------------------------------------
#    if [ "$count" -gt 1 ]; then
#        shellmock_debug "shelmock_replay: multiple matches: $count"
#        $CP "$BATS_TEST_DIRNAME/tmpstubs/$1.playback.state.tmp" "$BATS_TEST_DIRNAME/tmpstubs/$1.playback.state.bak"
#        # This script updates index for the next mock when there is more than one response value.
#        $CAT "$BATS_TEST_DIRNAME/tmpstubs/$1.playback.state.bak" | $AWK 'BEGIN{FS="@@"}{ if ((($3=="E" && $1=="'"$match"'")||($3=="P"&& index("'"$match"'",$1))||($3=="X" && match("'"$match"'",$1))) && (($4=="E" && $5=="'"$in_match"'")||($4=="P"&& index("'"$in_match"'",$5))||($4=="X" && match("'"$in_match"'",$5)))) printf("%s@@%d@@%s@@%s@@%s\n",$1,$2+1,$3,$4,$5) ; else printf("%s@@%d@@%s@@%s@@%s\n",$1,$2,$3,$4,$5) }' > "$BATS_TEST_DIRNAME/tmpstubs/$1.playback.state.tmp"
#    fi
#
#    #--------------------------------------------------------------
#    # If this is a command forwarding request then call the command
#    #--------------------------------------------------------------
#    if [ "$action" = "SOURCE" ]; then
#        shellmock_debug "shellmock_replay: perform: SOURCE *. $output*"
#        . $output
#        return $?
#
#    elif [ "$action" = "FORWARD" ]; then
#        local tmpcmd
#        $ECHO "$output" | $GREP "{}" > /dev/null
#
#        # SUBSTITION Feature
#        # If {} is present that means pass the match pattern into the exec script.
#        if [ $? -eq 0 ]; then
#            local tmpmatch=$(shellmock_escape_special_chars $match)
#            tmpcmd=$($ECHO "$output" | $SED "s/{}/$tmpmatch/g")
#        else
#            tmpcmd=$output
#        fi
#        shellmock_debug "shellmock_replay: perform: FORWARD *$tmpcmd*"
#        eval $tmpcmd
#        return $?
#
#    #----------------------------
#    # Otherwise return the output
#    #----------------------------
#    else
#        shellmock_debug "shellmock_replay: perform: OUTPUT *$output* STATUS: $status"
#        $ECHO "$output" | $AWK 'BEGIN{FS="%%"}{ for (i=1;i<=NF;i++) {print $i}}'
#        return $status
#    fi
# }
def main():

    #add_expect()
    mock_replay("cp", '"a b" c', 'd "e f"')
    mock_replay("cp", "'a b' c", 'd "e f"')
    mock_replay("cp", '"a b" d', 'd "e f"')
    mock_replay("cp", "'a b' d", "d 'e f'")

if __name__ == "__main__":
    main()