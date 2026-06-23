# vaspauto shell completion — subcommand names only (submit / run / analysis)
#
# Bash:  source completion.sh
# Zsh:   source completion.sh


_vaspauto_complete() {
    if [ "$COMP_CWORD" -eq 1 ] 2>/dev/null; then
        # bash
        COMPREPLY=($(compgen -W "submit run analysis" -- "${COMP_WORDS[1]}"))
    elif [[ "$words" != "" ]]; then
        # zsh
        compadd submit run analysis
    fi
}

# bash
if [ -n "$BASH_VERSION" ]; then
    complete -F _vaspauto_complete vaspauto
fi

# zsh
if [ -n "$ZSH_VERSION" ]; then
    # compdef only exists after compinit; silently skip if missing
    command -v compdef >/dev/null 2>&1 && compdef _vaspauto_complete vaspauto
fi
