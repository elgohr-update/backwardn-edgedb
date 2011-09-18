##
# Copyright (c) 2011 Sprymix Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import collections
import heapq
from datetime import timedelta, datetime

from semantix.utils.datastructures.all import Void


MAX_CONTROL_ID = 2**64 - 1


class ExpiringDict(collections.UserDict):
    """A dict-like object with an expiry time on its values.

    >>> dct = ExpiringDict(expiry=1.0)
    >>> dct['foo'] = 'bar'

    And, slightly after a second:
    >>> time.sleep(1.1)
    >>> 'foo' in dct
    ... False
    """

    def __init__(self, *, default_expiry:float=None):
        super().__init__()
        self.default_expiry = self._cast_expiry(default_expiry)
        self.keyheap = []
        self._control_idx = 0

    def _get_control_idx(self):
        self._control_idx += 1
        if self._control_idx == MAX_CONTROL_ID:
            self._control_idx = 0
        return self._control_idx

    def _cast_expiry(self, expiry):
        if expiry is None:
            return expiry

        if not isinstance(expiry, timedelta):
            if not isinstance(expiry, (int, float)):
                raise ValueError('expected expiry to be float or integer value, got {}:{!r}'. \
                                 format(type(expiry), expiry))
            expiry = timedelta(seconds=expiry)

        return expiry

    def _cleanup(self):
        now = datetime.now()

        if self.keyheap and self.keyheap[0][0] <= now:
            while self.keyheap and self.keyheap[0][0] <= now:
                data = heapq.heappop(self.keyheap)

                _, control = self.data[data[1]]
                if control == data[2]:
                    del self.data[data[1]]

    def set(self, key, value, *, expiry=Void):
        if expiry is Void:
            if self.default_expiry is not None:
                expiry = self.default_expiry
        else:
            expiry = self._cast_expiry(expiry)

        self._cleanup()

        control_idx = None

        if key in self:
            self.__delitem__(key)

        if expiry is not None and expiry is not Void:
            control_idx = self._get_control_idx()
            heapq.heappush(self.keyheap, (datetime.now() + expiry, key, control_idx))

        super().__setitem__(key, (value, control_idx))

    def __setitem__(self, key, value):
        self.set(key, value)

    def __getitem__(self, key):
        self._cleanup()
        return super().__getitem__(key)[0]

    def __iter__(self):
        self._cleanup()
        return super().__iter__()

    def __contains__(self, key):
        self._cleanup()
        return super().__contains__(key)

    def __len__(self):
        self._cleanup()
        return super().__len__()
