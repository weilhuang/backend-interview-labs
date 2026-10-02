"""先拒绝会误暴露/跨项目写数据的配置；负例只验证拒绝，不实际启动不安全容器。"""
def validate_compose(data):
    errors=[]
    if 'name' in data:errors.append('PROJECT_NAME_MUST_COME_FROM_DRIVER')
    for name,service in data.get('services',{}).items():
        for key in ['container_name','privileged','network_mode']:
            if key in service:errors.append(name+':FORBIDDEN_'+key)
        for port in service.get('ports',[]):
            if not isinstance(port,str) or not port.startswith('127.0.0.1:'):errors.append(name+':NON_LOOPBACK_PORT')
        if name=='redis' and service.get('ports'):errors.append('REDIS_MANAGEMENT_PORT_EXPOSED')
        for volume in service.get('volumes',[]):
            if not isinstance(volume,str) or volume.split(':')[0] not in data.get('volumes',{}):errors.append(name+':UNDECLARED_OR_HOST_VOLUME')
        image=service.get('image','')
        if ':latest' in image or (name=='redis' and image!='${REDIS_IMAGE}'):errors.append(name+':BYPASS_VERSION_LEDGER')
    for name,volume in data.get('volumes',{}).items():
        if volume:errors.append(name+':EXTERNAL_OR_FIXED_VOLUME_NAME')
    return errors
