/*
 * Minimal ZIP writer (STORE method, no compression).
 * PNGs are already internally compressed, so storing them adds ~0 bytes while
 * keeping this dependency-free, offline-safe, and CSP-clean (no CDN, no
 * bundler). Exposes window.makeZip(files) -> Blob, where files is
 * [{ name: string, data: Uint8Array }].
 */
(function () {
  "use strict";

  var CRC_TABLE = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) {
        c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      }
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) {
      c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    }
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  function strBytes(s) {
    return new TextEncoder().encode(s);
  }

  function dosDateTime(d) {
    var time = ((d.getHours() & 0x1f) << 11) |
               ((d.getMinutes() & 0x3f) << 5) |
               ((Math.floor(d.getSeconds() / 2)) & 0x1f);
    var date = (((d.getFullYear() - 1980) & 0x7f) << 9) |
               (((d.getMonth() + 1) & 0xf) << 5) |
               (d.getDate() & 0x1f);
    return { time: time, date: date };
  }

  function makeZip(files) {
    var now = dosDateTime(new Date());
    var parts = [];        // local headers + data, in order
    var central = [];      // central directory records
    var offset = 0;

    files.forEach(function (f) {
      var nameBytes = strBytes(f.name);
      var data = f.data;
      var crc = crc32(data);
      var size = data.length >>> 0;

      var lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true);
      lh.setUint16(4, 20, true);       // version needed
      lh.setUint16(6, 0x0800, true);   // flags: UTF-8 filename
      lh.setUint16(8, 0, true);        // method: STORE
      lh.setUint16(10, now.time, true);
      lh.setUint16(12, now.date, true);
      lh.setUint32(14, crc, true);
      lh.setUint32(18, size, true);    // compressed size
      lh.setUint32(22, size, true);    // uncompressed size
      lh.setUint16(26, nameBytes.length, true);
      lh.setUint16(28, 0, true);       // extra length
      var lhBytes = new Uint8Array(lh.buffer);

      parts.push(lhBytes, nameBytes, data);
      var localOffset = offset;
      offset += lhBytes.length + nameBytes.length + data.length;

      var ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true);
      ch.setUint16(4, 20, true);       // version made by
      ch.setUint16(6, 20, true);       // version needed
      ch.setUint16(8, 0x0800, true);   // flags
      ch.setUint16(10, 0, true);       // method
      ch.setUint16(12, now.time, true);
      ch.setUint16(14, now.date, true);
      ch.setUint32(16, crc, true);
      ch.setUint32(20, size, true);
      ch.setUint32(24, size, true);
      ch.setUint16(28, nameBytes.length, true);
      ch.setUint16(30, 0, true);       // extra length
      ch.setUint16(32, 0, true);       // comment length
      ch.setUint16(34, 0, true);       // disk number
      ch.setUint16(36, 0, true);       // internal attrs
      ch.setUint32(38, 0, true);       // external attrs
      ch.setUint32(42, localOffset, true);
      central.push(new Uint8Array(ch.buffer), nameBytes);
    });

    var cdStart = offset;
    var cdSize = central.reduce(function (a, c) { return a + c.length; }, 0);

    var eocd = new DataView(new ArrayBuffer(22));
    eocd.setUint32(0, 0x06054b50, true);
    eocd.setUint16(4, 0, true);
    eocd.setUint16(6, 0, true);
    eocd.setUint16(8, files.length, true);
    eocd.setUint16(10, files.length, true);
    eocd.setUint32(12, cdSize, true);
    eocd.setUint32(16, cdStart, true);
    eocd.setUint16(20, 0, true);

    var all = parts.concat(central);
    all.push(new Uint8Array(eocd.buffer));
    return new Blob(all, { type: "application/zip" });
  }

  window.makeZip = makeZip;
})();
