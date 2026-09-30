create table stock(sku varchar(64) primary key,remaining integer not null);
create table orders(request_id varchar(128) primary key,quantity integer not null);
insert into stock(sku,remaining) values('BOOK',10);
