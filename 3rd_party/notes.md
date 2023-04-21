## prerequisites
### influxdb 2.0
* https://docs.influxdata.com/influxdb/v2.0/get-started/?t=Linux
* set custom db path in */etc/influxdb/config.toml*  
set db path owner with *sudo chown influxdb:influxdb <influxdb_folder>*
* setup through *localhost:8086*
* python package *pip3 install [influxdb_client[ciso]](https://github.com/influxdata/influxdb-client-python)*
### redis
* *sudo pip3 install redis*
* *pip3 install aioredis*
* ?*pip3 install aioredis-opentracing*
* *sudo apt install redis-server*
* *sudo systemctl enable redis-server*
### [arctic](https://arctic.readthedocs.io/en/latest/)
* *pip3 install git+https://github.com/manahl/arctic.git*
* install [mongoDB](https://docs.mongodb.com/manual/tutorial/install-mongodb-on-ubuntu/)
* set mongoDB db path in */etc/mongod.conf*  
set db path owner with *sudo chown mongodb:mongodb <mongodb_folder>*

### crpytostore, crpytofeed
* install from 3rd_party dir with *pip3 install --editable .*

### tectonicdb
```
./3rd_party/tectonicdb$ ./target/debug/tdb-server -f ./db/ -vvvvvv -a -i 10000
$ cargo build --release
```
#### libtdb-core.so
```
./crates/tdb-core/Cargo.toml
    +[lib]
    +name = "tdb_core"
    +#crate_type = ["dylib"]
   
$ ./crates/tdb-core
$ cargo build --lib
```

#### dask + parquet
```
pip3 install brotlipy
pip3 install fastparquet

pip3 install pyarrow
```
