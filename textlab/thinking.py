"""Translate task thinking intent into explicit provider-specific request fields."""
from copy import deepcopy


def thinking_body(profile, level, extra):
    body = deepcopy(extra)
    if level == 'default' or profile.provider == 'mock':
        return body
    if profile.provider == 'ollama':
        if level == 'minimal':
            raise ValueError('Ollama does not have a minimal thinking level; use low instead')
        key, value = 'think', {'off':False,'on':True}.get(level,level)
    elif profile.thinking_adapter == 'chat_template':
        if level not in ('on','off'):
            raise ValueError('The chat-template adapter supports on/off only. Use reasoning_effort for graded levels.')
        kwargs = body.setdefault('chat_template_kwargs',{})
        if not isinstance(kwargs,dict):
            raise ValueError('chat_template_kwargs must be an object')
        enabled = level == 'on'
        if 'enable_thinking' in kwargs and kwargs['enable_thinking'] != enabled:
            raise ValueError('Thinking setting conflicts with chat_template_kwargs.enable_thinking')
        if 'reasoning_effort' in body:
            raise ValueError('Remove reasoning_effort when using explicit chat-template thinking control')
        kwargs['enable_thinking'] = enabled
        return body
    else:
        key, value = 'reasoning_effort', {'off':'none','on':'medium'}.get(level,level)
        kwargs = body.get('chat_template_kwargs',{})
        if isinstance(kwargs,dict) and 'enable_thinking' in kwargs:
            raise ValueError('Remove enable_thinking when using explicit reasoning_effort control')
    if key in body and body[key] != value:
        raise ValueError(f'Thinking setting conflicts with extra_body.{key}')
    body[key] = value
    return body
