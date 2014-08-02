_UUID_GLOB = '????????-????-????-????-????????????'

_REDIS_CONF_DEFAULT = {'redis_host': "localhost",
                       'redis_port': 6379,
                       'redis_db': 4}

### Exceptions

class DatatypesError(Exception):
    """Base class for Datatypes Exceptions"""

    def __init__(self, *args, **kwargs):
        super(DatatypesError, self).__init__(*args, **kwargs)

class UUIDRedisFactoryError(DatatypesError):
    """Base class for UUID Redis Object Exceptions"""

    def __init__(self, *args, **kwargs):
        super(UUIDRedisFactoryError, self).__init__(*args, **kwargs)

class UUIDRedisObjectError(DatatypesError):
    """Base class for UUID Redis Object Exceptions"""

    def __init__(self, *args, **kwargs):
        super(UUIDRedisObjectError, self).__init__(*args, **kwargs)

class UUIDRedisObjectDNE(UUIDRedisObjectError):
    """UUID Redis Object Does Not Exist"""

    def __init__(self, obj):
        msg = "{:s} does not exist.".format(obj)
        super(UUIDRedisObjectDNE, self).__init__(msg)


### Objects

class RedisObjectBase(object):

    @classmethod
    def from_new(cls, key=None):
        """New Constructor"""

        obj = cls(key)

    @classmethod
    def from_existing(cls, key):
        """Existing Constructor"""

        obj = cls(key)

        # Verify Object in DB
        if not obj.db.exists(obj.full_key):
            raise UUIDRedisObjectDNE(obj)

        return obj

    def __init__(self, key=None):
        """Base Constructor"""

        super(RedisObjectBase, self).__init__()

        self.obj_key = key
        self.full_key = ""

        if self.pre_key is not None:
            self.full_key = "{:s}".format(self.pre_key).lower()

        if self.obj_key is not None:
            self.full_key += "{:s}".format(self.obj_key).lower()

        if (len(self.full_key) == 0):
            raise RedisObjectError("Either pre_key or full_key required")

    def __unicode__(self):
        """Return Unicode Representation"""

        u = u"{:s}".format(type(self).__name__)
        if self.obj_key is not None:
            u += u"_{:s}".format(self.obj_key)
        return u

    def __str__(self):
        """Return String Representation"""

        s = unicode(self).encode(_ENCODING)
        return s

    def __repr__(self):
        """Return Unique Representation"""

        r = "{:s}".format(self.full_key)
        return r

    def __hash__(self):
        """Return Hash"""

        return hash(repr(self))

    def __eq__(self, other):
        """Test Equality"""

        return (repr(self) == repr(other))

    def delete(self):
        """Delete Object"""

        if not self.db.delete(self.full_key):
            raise UUIDRedisObjectError("Delete Failed")


class RedisHashBase(RedisObjectBase):
    """
    Redis Hash Base Class

    """

    schema = _BASE_SCHEMA

    @classmethod
    def from_new(cls, d, key=None):
        """New Constructor"""

        # Call Parent
        obj = super(RedisHashBase, cls).from_new(key)

        # Set Times
        data = copy.deepcopy(d)
        data['created_time'] = str(time.time())
        data['modified_time'] = str(time.time())

        # Check dict
        if (set(data.keys()) != set(obj.schema)):
            raise KeyError("Keys {:s} do not match schema {:s}".format(data.keys(), obj.schema))

        # Add Object Data to DB
        if not obj.db.hmset(obj.full_key, data):
            raise UUIDRedisObjectError("Create Failed")

        # Return Object
        return obj

    def __getitem__(self, k):
        """Get Dict Item"""

        if k in self.schema:
            return self.db.hget(self.full_key, k)
        else:
            raise KeyError("Key {:s} not valid in {:s}".format(k, self))

    def __setitem__(self, k, v):
        """Set Dict Item"""

        if k in self.schema:
            return self.db.hset(self.full_key, k, v)
        else:
            raise KeyError("Key {:s} not valid in {:s}".format(k, self))

    def get_dict(self):
        """Get Full Dict"""

        data = self.db.hgetall(self.full_key)
        return data

    def set_dict(self, d):
        """Set Full Dict"""

        data = copy.deepcopy(d)
        data['modified_time'] = str(time.time())
        if not set(data.keys()).issubset(set(self.schema)):
            raise KeyError("Keys {:s} do not match schema {:s}".format(data.keys(), self.schema))
        self.db.hmset(self.full_key, data)


class RedisSetBase(RedisObjectBase):
    """
    Redis Set Base Class

    """

    @classmethod
    def from_new(cls, vals, key=None):
        """New Constructor"""

        # Call Parent
        obj = super(UUIDRedisSetBase, cls).from_new(key)

        # Add lst to DB
        if not obj.db.sadd(obj.full_key, *vals):
            raise UUIDRedisObjectError("Create Failed")

        # Return Object
        return obj

    def get_vals(self):
        """Get All Vals from Set"""

        return self.db.smembers(self.full_key)

    def add_vals(self, *vals):
        """Add Vals to Set"""

        if not self.db.sadd(self.full_key, *vals):
            raise UUIDRedisObjectError("Add Failed")

    def del_vals(self, *vals):
        """Remove Vals from Set"""

        if not self.db.srem(self.full_key, *vals):
            raise UUIDRedisObjectError("Remove Failed")


class RedisFactory(object):

    def __init__(self, redis_db, base_cls, prefix=None):

        # Call Super
        super(RedisFactory, self).__init__()

        # Check Input
        if not issubclass(base_cls, RedisObjectBase):
            raise RedisFactoryError("cls must be subclass of UUIDRedisObjectBase")
        base_name = base_cls.__name__
        if not base_name.endswith(_SUF_BASE):
            raise UUIDRedisFactoryError("cls name must end with '{:s}'".format(_SUF_BASE))

        # Setup Class Name
        cls_name = base_name[0:base_name.rfind(_SUF_BASE)]

        # Setup DB
        self.db = redis_db

        # Setup Base Key
        if prefix == None:
            self.pre_key = None
        else:
            self.pre_key = prefix

        # Setup Class
        class cls(base_cls):

            pre_key = self.pre_key
            db = self.db

        cls.__name__ = cls_name
        self.cls = cls

    def list_objs(self):
        """List Factory Objects"""
        obj_lst = self.db.keys("{:s}:{:s}".format(self.pre_key, _UUID_GLOB))
        obj_uuids = []
        for full_key in obj_lst:
            obj_uuid = full_key.split(':')[-1]
            obj_uuids.append(obj_uuid)
        return set(obj_uuids)

    def get_objs(self):
        """Get Factory Objects"""
        obj_lst = self.db.keys("{:s}:{:s}".format(self.pre_key, _UUID_GLOB))
        objs = []
        for full_key in obj_lst:
            obj_uuid = full_key.split(':')[-1]
            obj = cls.from_existing(obj_uuid)
            objs.append(obj)
        return objs

    def from_new(self, *args, **kwargs):
        return self.cls.from_new(*args, **kwargs)

    def from_existing(self, *args, **kwargs):
        return self.cls.from_existing(*args, **kwargs)