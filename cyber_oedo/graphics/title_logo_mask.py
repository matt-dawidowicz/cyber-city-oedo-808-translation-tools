"""Store the approved antialiased opening-logo coverage mask.

The mask was derived from the user-supplied 1448-by-1086 logo reference. The
source was proportionally resized to 256-by-192 with Lanczos resampling and
centered vertically in the 256-by-240 hardware frame. Luminance 8 is the
reviewed black point and 200 is the white point; values between them retain
four bits of edge coverage. This keeps the pale master lettering solid while
using the PC Engine palette to smooth curves and diagonals.

Two coverage values are packed per byte, most-significant nibble first, then
compressed with zlib level 9 and Base85 encoded. This is original replacement
artwork, not extracted game content. Keeping the reviewed coverage mask as
text makes the default build deterministic and avoids a runtime Pillow
dependency. ``title_screen.py --source-image`` provides the documented path
for regenerating a replacement from another master image.
"""

from __future__ import annotations


LOGO_MASK_WIDTH = 256
LOGO_MASK_HEIGHT = 240
LOGO_MASK_BITS_PER_PIXEL = 4
LOGO_MASK_PACKED_BYTES = 30720
LOGO_MASK_PACKED_SHA256 = (
    "2d48dae1c9807a4a0d6dbe224ab19183"
    "4aa40b3e1c4510437d6b20a5224dcbc7"
)
LOGO_MASK_B85 = (
    'c-rk;d2C$88K1p;$61n4K_S_VU4m2&FHQ=oN@YWgL_x@=O`_6L>|PG43U)yap$E1QYBm94E2'
    '^5fg>HIKK@K^zm4GC*4Jw5OC+q%!1T@Y%E#(UFHa^yCdv~XEym@b~_jc_Ks1oldOWAkK{ARx'
    'IoA3MPo8185!i5VLE?l^9;lhOr7cN}5aN)v*3l}b2xcFqCwh3W<5P;?D$+fR33|2G|T!Svj$'
    'Mx%PL=V;ytY!^8wdkrIH3ZATz*9r98hr|qr)$Fn(ccRR=EEQk_u_Vg@DNDQo3IynjZY9iXEz'
    'B-=ykRYy)z3MjE7kef+_sC6;2dFU&8ty0nKn8-B<~8VGp~R27Z&DyGal;E@yxbHEd;1gJlr5'
    '0T6(&yAb|r2oLxDa$g)y;wFaxn&kxWB;lTDbo-+)gZcX~cH^6e_wCy^fTl>~3*ni=`;XvDKj'
    'Ob)cz6KjhF^ODfF3vv&}3!{5`P^cMkvQ^THze1gfN1ra+Ct|&oOl;$W1SOh8|?Gp7E=GA~@O'
    'y`4={NO*Q4^A0q#5yq)Nxw;zuOO_flgemVXmop_w`2aE|`yMf4`@J`V;`{C5p^j3Z}V3{*?z'
    '$_X&ku4VWLDV6V|M8Q<!^6)qes3~k@TXZbnI8!t$#+{YKQ_i`s#}Uq)BYxj{`Vh7`cLKK2ZI'
    'o1K%x9Y+*KEuKBgKyIeh#SvTekVr%&c@45ix`>x{%-X7X1+_>Thlnf}|qNgJlAsv)thIApd('
    'Z&JK1%zw=Wl^-NwxM2PXD!UZzA_WYirg9AWt#y>l)z{Rl{k$Pszp)MzFsSk;a=`-mm%!XJXs'
    'Hj<w#G1!{<pNZw{M1+KO05Zw#Bsnq`CfIMGu~UIZzD0>Hmg=`5QOqE&mr`{E4jS|7Mwv%8d0'
    '-g;Hqvxrg>LM;eqGT`>RuESj6?|C7`b;)ZFL(Lv_A(K~ar@g(bXFuTC`S8t5h2wKZ&sKfEEw'
    'zj?o$2oM9M!sb%0Q#DmHf(H);CHT}J()&lzT?8h|2Zz(adh;xr@wvvI$XAHec|Tsf6`drZ?&'
    '*nfp+Blu>WKD?nVr>xV-C7D!P_owbsY1If(tjhmRCSe-ZO^$dNp3+zUZ14&h)SAp2aS+@JSx'
    '_V9zo0_e*q^JtO_tRV2D9sk8~`R4B>`WQF5mb~-<!uwPhEdLrA2W!z|!w<au^4&iP9g>FgyS'
    'E<1|7Ifj_{nJhNIqUqLkTYy2}4F|MKC^U$PE65>+g&B#=F=oZl#&IGcLt1rTC!_@u@~8O0d0'
    'ef5Li3S$820&vir_Ict^yZVq=bk=esbx^3hGan>;DxHx>@PO?EUQadxb^O1{bK6@j353}>EV'
    '-#McX*~igmKiZI95HfhPERy>Fc?w%<-|#QKkdYypcyW(l19jqJ%!(|<wv_5ZVDaT8Ui$Na7q'
    'IzI7wPc@7D7prZEkFfTl(kVTRvKAndj0@1kkFg;wi^%3r4Cr&c>+37qS%Qc#C#ef(aUpvsb%'
    '$`2Ac`J?pJyo^cnrJ0+p1y&ka9T1lfwI&UJhj#v!0{omRI3u!EKr?4<yg`oH@UPO&pSC%~q$'
    'l*(Dl1rkw02Eprfm2@P|I&xQM1w?(aoF<J=M->X)nkOV9?fm%KUZgdQj=FOwq9Na4%2>OdR5'
    '%XuG$BZTYJVEAv9d;rgNA5P*iOP4x(5Nl5(hHd}r=j~43uIB#Y;lo7jqw`{J=osOvd35h=~P'
    'jaszhlpxolMdcT+9gt(m{9or(4OCGjJZy;+It*=@Sx-^fm!yLR`{zN_~`<ipo>lFuT@>*z^V'
    '{v7Ds}0F4}+0iJ#n<qH~?o=s4%#ebdt2IO{~1{}-SWzaeDVF0Dj1XuteZy2YJg1DWsZL+MZ7'
    '0CeQ<qQp9nQLV8_!EC2>`Cyjub8z7ApfXEn=41I2HS>j3Z9p~H+`{;Yk<HPyF3qRP@C~+Qmq'
    '{&ua6$Yuj#2(8U5IV7pT9GI_UMr#M~07o?EFmrhBjC9e+2w~t^P&(OIh#c*MCCOpM(B=T7Gf'
    ';rK~BoiGEYzPtz7!`)joKKhrv=Jg4wi<XwL=a>U}+U)bLN&glH#jKc5F>;I;-v1XMf#tBoE{'
    'H0|?aVh?`<njMT{F#+&%h0wE-=m35UNip2o%4^hEVD5hYvwiaXVxM8&FU7#5bM;kjxU8pxy{'
    'Hj+e>ww)x_Uv+jB3)Hmn>fZrf7k_Ze%fT+?5SiBp4e&DylKBnchAFQVZuF=DJ=)88OhQqVhq'
    'Ue#VRz>Yt3PQzcxmTW>vc0Km)k99Pn+QhUif5(W1Kg5<ym(pLrVfh(kldAh0v*l0h)$n&P+K'
    '|#;g@gHXf|KOcV#i-fq$~3$Ser71E#zQ+%mBi&`DcI~e~743;t!Z@$U+pP-QlqPVIHVgHor+'
    '*{<yU>o6)uDkT*aHC-ocAX;L0gryYM46_&)`Z<#nz_c>{0PTSXCh`=(E_nike{JsR8i&&W}<'
    'BW);0CSQ!oesepMExw`7Lda4?J>qG?@TxkQ>SKXj;FwWQIvyL!H{M%Tr|Ns7`+zef2Hu6Pe^'
    'HqXq-=h1p!oY?;D4Hue6iG|HiwYFn3FIjn2|x-Xi(X20q>C%3J@WHBx%;2>eM-dsW&3e9Ed!'
    'pV^H@bx__zk^YR>{Aqf8=?oHtW^q`#aFA1;Kd$AU)YaeT!m`JE9Z%@;q-J}m;x-bspN{?tT9'
    'tTkaZ-N(at>THsL+eMJ5u$Y|JkO;NWTS~fP91N>(4@IM8%l$B>M+R!JeJg!(3Y-2SB%)ubW3'
    'HUUtB=uE_v3!wB$i!pBjYw`_g@W6K6Lwe{S?`kOC^9xbiMh~s{~5u6{a8K9C07u>?Tj(q*=y'
    'kYrG8_#QhpCoubx3#Zt+jn%z^VDu?|B6<tpV=IZZrczpp56Ps1UuQ3t2UlHPLNgds$!=%pD-'
    '5CbCDwH1Dt!wc8b~3ugwP!+dM#zeoz#BiQxAH_u=C`@^ASEf=A4C7NdIFRc`n=9Y-c8?PTD|'
    ';iR0>cTwV#Mw@IAMsPJ@e+2d5y@Pc2FY^&OSDn8dJ^2aw6cl$%Pp!snbQPF|*dBNM1}+x14g'
    'u~oxm6fhKc|mUr{jkFs1k-R9Nx8Z7i5^ZFh`jdw!1@%<?j$QTh1lNeqpDwip!Hi!kI^j^MPL'
    ';B!vCDmz!Cgu(R`XMU5`8zMHTwx93;Cw0(+OeZ|EpR=>4Ph>JCcm~FW|KYY@@E@pOJD&@j;*'
    '0xTXa7PgaC?(@$mRU>TQ_{wD-YlYJ&JVv&nx!TG9&=aDmu@4P9bU|N!{_Y%lEUCEb+7`HQgI'
    'S@e@q;UwLjX|kl+m_tm(GN6}NNdik}pAJkyKiCuWt6@UfuN%;^QKTF1ndLeZ%w|5r|&f-lYI'
    '$vX4iYq^||a){MxKBTI^fdPHK6XxG><#m8C_rec1Js9UsZkv@Ns&z~auA<@Z?^`zAO{3?Fi;'
    'sUkY1j21&d1FuWjd-6kF+0~0Y#uB!FTmHyMnJ#I;9TLCk)`d;?i#4V`fj8`<0r!RMt1F&ii9'
    'CYs&t-*!=TTrUd4{B^20F>ahk}k$y7+%idpP?)`mUmT!c)gNkXjOl+ijx9~~h`$c8I4@q0=U'
    ';+GhI#dG|h`WsS7v26B$ej*3@?S#R9NV+~0Mwpn7Y<rkd5=hNP28&NsHHed|9*Oke*?aIVLv'
    'R&|Hb&>(=SHO0`(|Hu>WS`mrI=g$Sjh+R6MJ@)SP3#&H9V5^P)~sg1tqApD8KGon}!bt@^*9'
    'VF+m{FijO9{$9z+&j`^*7;1)ze?$_@;t~KU{V?X1W$`bgoLr>U^us(0T5S54QS5;U87g)CDY'
    'i7j@{z)#3P~lhl>IEol_+20=r_dfkuw92{dspm=AYK_d!X)I0VfAu<;XGVbl{brU!8vth+ho'
    '0q#U%J|Dxm{kmpirb}k<ym6@VSN}BO4eh2K4wOnO7z*1>vwo3e#WVbZ3?Bdq{pya%{<H5K%s'
    '~%Ixt<qNxLq%+W8^pH!uA@#E8n-i+zw+7d@O{6+!k=m8E4c!QUsxL}t$|73d91Mix>ce39~R'
    '33kT<$!PS0L`&)dqE`F-)C_CNGMp2qU)5<)SHezQ8P)MAWbX79tFFB@FE_u=**@Z>Z5Pe3V>'
    'Ucyq+<v$gp@s;$=5An}330^89{fvpZ++UTkogIbp?<(#U+q_d$^>?T3FH87y74df^LeBhhk@'
    '^44<`(R&+a=+A-7d$ze1JVUb6@f0_iJ|?J$~}=FK$#Ht@sf#i?c6iekXO=g9nC(kL~{QM}9b'
    'P!3DsD3m4}X{_*6C{@nQ4V0=8;QkEO<1%2SEB#OnagUZfT<Kt7F{@mLn3Y?9A{&5uH(A#Ig%'
    'V1^1pB%@T;lTI@ATXZn^_)2MBDih*!(i-WqVRp#l5{lfjpm|YYa$w{dw$0hI0_o}?3nbVz|!'
    '7}9#8KoP4B^nUa_qYjRa<+yHG%k&Tj)L5NcWSMjuXhGh1VA)vrWb%4Z&!1*2QHfv?8)6dnkd'
    'c7pc-{sUbo4+^7>kAMaMraaT2x)+p>;6IF`plqzvC<LQG^Ez1CxRfT_Z-b@XArzl04uQjf)X'
    'nM^unVf*RgcKuM4xt|hS#i1k@-J*8V#hn8&r&evNWDFIDq&|QV$SH6oUV`J=R$L#&(=Cp^uT'
    '!^V?g>Ut0er7>zzmrct>3Np^+#A3_bUKpEu$&@ehagyc`>UzQ#HH{mZGD=`whcL6wcD$%$kH'
    ';QwS#OSGT=<JEka-1k%KRO;<5P$XW>Srl`58|&yW7&_|d$9bMit<PN#uuCrKhi&we+tVV#l?'
    '!3>Tx&d<3jkCb~F7W{<_Al2-1J^4J)QWdRZNv{{;D2{6Otz$4dWe^3P!YUF6AZO+#<!zWQM0'
    '5I6>E>suGhkLLe@G5^M@b6EfQkS~Vw{PHoJ=T6f!w3Fk12iboqRR>DeBS`jpk^LP*iR}Es^z'
    'RFUdVv4Ha<sGoxB=7x|HchL;A=wJs5gTDI{^Fxf6v-_;4!j~)%edBM3cotwe{$_rY7hKf(yX'
    '18g$F+x>Xl0T)1%I!i5VLE?l^9;lhOr7cN}5aN)wm$ASL=6+(;g'
)
