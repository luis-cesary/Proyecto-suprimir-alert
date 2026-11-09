class Groups:
    def __init__(self, api):
        self.api = api

    def list(self, search=''):
        params = {'output': ['groupid', 'name'], 'sortfield': 'name'}
        if search:
            params['search'] = {'name': search}
        return self.api.call('hostgroup.get', params)

    def select(self, groups, selection):
        if selection.startswith('id:'):
            matches = [g for g in groups if g['groupid'] == selection[3:]]
            if matches:
                return matches[0]
        elif selection.isdigit() and 1 <= int(selection) <= len(groups):
            return groups[int(selection) - 1]
        else:
            matches = [g for g in groups if g['groupid'] == selection or g['name'] == selection]
            if matches:
                return matches[0]
        raise ValueError('Grupo inexistente o sin acceso; use número o id:GROUPID.')
