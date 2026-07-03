/* poise-card 0.137.0 — bundled, served by the Poise integration (ADR-0040) */
var W=globalThis,G=W.ShadowRoot&&(W.ShadyCSS===void 0||W.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,ot=Symbol(),bt=new WeakMap,H=class{constructor(t,e,n){if(this._$cssResult$=!0,n!==ot)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(G&&t===void 0){let n=e!==void 0&&e.length===1;n&&(t=bt.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),n&&bt.set(e,t))}return t}toString(){return this.cssText}},vt=o=>new H(typeof o=="string"?o:o+"",void 0,ot),O=(o,...t)=>{let e=o.length===1?o[0]:t.reduce((n,r,i)=>n+(s=>{if(s._$cssResult$===!0)return s.cssText;if(typeof s=="number")return s;throw Error("Value passed to 'css' function must be a 'css' function result: "+s+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+o[i+1],o[0]);return new H(e,o,ot)},yt=(o,t)=>{if(G)o.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of t){let n=document.createElement("style"),r=W.litNonce;r!==void 0&&n.setAttribute("nonce",r),n.textContent=e.cssText,o.appendChild(n)}},it=G?o=>o:o=>o instanceof CSSStyleSheet?(t=>{let e="";for(let n of t.cssRules)e+=n.cssText;return vt(e)})(o):o;var{is:Gt,defineProperty:Xt,getOwnPropertyDescriptor:Yt,getOwnPropertyNames:Jt,getOwnPropertySymbols:Zt,getPrototypeOf:Qt}=Object,X=globalThis,$t=X.trustedTypes,te=$t?$t.emptyScript:"",ee=X.reactiveElementPolyfillSupport,T=(o,t)=>o,st={toAttribute(o,t){switch(t){case Boolean:o=o?te:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,t){let e=o;switch(t){case Boolean:e=o!==null;break;case Number:e=o===null?null:Number(o);break;case Object:case Array:try{e=JSON.parse(o)}catch{e=null}}return e}},wt=(o,t)=>!Gt(o,t),xt={attribute:!0,type:String,converter:st,reflect:!1,useDefault:!1,hasChanged:wt};Symbol.metadata??=Symbol("metadata"),X.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=xt){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let n=Symbol(),r=this.getPropertyDescriptor(t,n,e);r!==void 0&&Xt(this.prototype,t,r)}}static getPropertyDescriptor(t,e,n){let{get:r,set:i}=Yt(this.prototype,t)??{get(){return this[e]},set(s){this[e]=s}};return{get:r,set(s){let a=r?.call(this);i?.call(this,s),this.requestUpdate(t,a,n)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??xt}static _$Ei(){if(this.hasOwnProperty(T("elementProperties")))return;let t=Qt(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(T("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(T("properties"))){let e=this.properties,n=[...Jt(e),...Zt(e)];for(let r of n)this.createProperty(r,e[r])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[n,r]of e)this.elementProperties.set(n,r)}this._$Eh=new Map;for(let[e,n]of this.elementProperties){let r=this._$Eu(e,n);r!==void 0&&this._$Eh.set(r,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let n=new Set(t.flat(1/0).reverse());for(let r of n)e.unshift(it(r))}else t!==void 0&&e.push(it(t));return e}static _$Eu(t,e){let n=e.attribute;return n===!1?void 0:typeof n=="string"?n:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let n of e.keys())this.hasOwnProperty(n)&&(t.set(n,this[n]),delete this[n]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return yt(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,n){this._$AK(t,n)}_$ET(t,e){let n=this.constructor.elementProperties.get(t),r=this.constructor._$Eu(t,n);if(r!==void 0&&n.reflect===!0){let i=(n.converter?.toAttribute!==void 0?n.converter:st).toAttribute(e,n.type);this._$Em=t,i==null?this.removeAttribute(r):this.setAttribute(r,i),this._$Em=null}}_$AK(t,e){let n=this.constructor,r=n._$Eh.get(t);if(r!==void 0&&this._$Em!==r){let i=n.getPropertyOptions(r),s=typeof i.converter=="function"?{fromAttribute:i.converter}:i.converter?.fromAttribute!==void 0?i.converter:st;this._$Em=r;let a=s.fromAttribute(e,i.type);this[r]=a??this._$Ej?.get(r)??a,this._$Em=null}}requestUpdate(t,e,n,r=!1,i){if(t!==void 0){let s=this.constructor;if(r===!1&&(i=this[t]),n??=s.getPropertyOptions(t),!((n.hasChanged??wt)(i,e)||n.useDefault&&n.reflect&&i===this._$Ej?.get(t)&&!this.hasAttribute(s._$Eu(t,n))))return;this.C(t,e,n)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:n,reflect:r,wrapped:i},s){n&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,s??e??this[t]),i!==!0||s!==void 0)||(this._$AL.has(t)||(this.hasUpdated||n||(e=void 0),this._$AL.set(t,e)),r===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,i]of this._$Ep)this[r]=i;this._$Ep=void 0}let n=this.constructor.elementProperties;if(n.size>0)for(let[r,i]of n){let{wrapped:s}=i,a=this[r];s!==!0||this._$AL.has(r)||a===void 0||this.C(r,void 0,i,a)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(n=>n.hostUpdate?.()),this.update(e)):this._$EM()}catch(n){throw t=!1,this._$EM(),n}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[T("elementProperties")]=new Map,w[T("finalized")]=new Map,ee?.({ReactiveElement:w}),(X.reactiveElementVersions??=[]).push("2.1.2");var ht=globalThis,At=o=>o,Y=ht.trustedTypes,Ct=Y?Y.createPolicy("lit-html",{createHTML:o=>o}):void 0,Lt="$lit$",A=`lit$${Math.random().toFixed(9).slice(2)}$`,Rt="?"+A,ne=`<${Rt}>`,k=document,I=()=>k.createComment(""),U=o=>o===null||typeof o!="object"&&typeof o!="function",mt=Array.isArray,re=o=>mt(o)||typeof o?.[Symbol.iterator]=="function",at=`[ 	
\f\r]`,D=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Et=/-->/g,St=/>/g,E=RegExp(`>|${at}(?:([^\\s"'>=/]+)(${at}*=${at}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),kt=/'/g,Pt=/"/g,Ht=/^(?:script|style|textarea|title)$/i,ft=o=>(t,...e)=>({_$litType$:o,strings:t,values:e}),m=ft(1),Ie=ft(2),Ue=ft(3),P=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),Mt=new WeakMap,S=k.createTreeWalker(k,129);function Ot(o,t){if(!mt(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return Ct!==void 0?Ct.createHTML(t):t}var oe=(o,t)=>{let e=o.length-1,n=[],r,i=t===2?"<svg>":t===3?"<math>":"",s=D;for(let a=0;a<e;a++){let c=o[a],u,f,h=-1,b=0;for(;b<c.length&&(s.lastIndex=b,f=s.exec(c),f!==null);)b=s.lastIndex,s===D?f[1]==="!--"?s=Et:f[1]!==void 0?s=St:f[2]!==void 0?(Ht.test(f[2])&&(r=RegExp("</"+f[2],"g")),s=E):f[3]!==void 0&&(s=E):s===E?f[0]===">"?(s=r??D,h=-1):f[1]===void 0?h=-2:(h=s.lastIndex-f[2].length,u=f[1],s=f[3]===void 0?E:f[3]==='"'?Pt:kt):s===Pt||s===kt?s=E:s===Et||s===St?s=D:(s=E,r=void 0);let $=s===E&&o[a+1].startsWith("/>")?" ":"";i+=s===D?c+ne:h>=0?(n.push(u),c.slice(0,h)+Lt+c.slice(h)+A+$):c+A+(h===-2?a:$)}return[Ot(o,i+(o[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),n]},N=class o{constructor({strings:t,_$litType$:e},n){let r;this.parts=[];let i=0,s=0,a=t.length-1,c=this.parts,[u,f]=oe(t,e);if(this.el=o.createElement(u,n),S.currentNode=this.el.content,e===2||e===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(r=S.nextNode())!==null&&c.length<a;){if(r.nodeType===1){if(r.hasAttributes())for(let h of r.getAttributeNames())if(h.endsWith(Lt)){let b=f[s++],$=r.getAttribute(h).split(A),x=/([.?@])?(.*)/.exec(b);c.push({type:1,index:i,name:x[2],strings:$,ctor:x[1]==="."?lt:x[1]==="?"?dt:x[1]==="@"?ut:L}),r.removeAttribute(h)}else h.startsWith(A)&&(c.push({type:6,index:i}),r.removeAttribute(h));if(Ht.test(r.tagName)){let h=r.textContent.split(A),b=h.length-1;if(b>0){r.textContent=Y?Y.emptyScript:"";for(let $=0;$<b;$++)r.append(h[$],I()),S.nextNode(),c.push({type:2,index:++i});r.append(h[b],I())}}}else if(r.nodeType===8)if(r.data===Rt)c.push({type:2,index:i});else{let h=-1;for(;(h=r.data.indexOf(A,h+1))!==-1;)c.push({type:7,index:i}),h+=A.length-1}i++}}static createElement(t,e){let n=k.createElement("template");return n.innerHTML=t,n}};function M(o,t,e=o,n){if(t===P)return t;let r=n!==void 0?e._$Co?.[n]:e._$Cl,i=U(t)?void 0:t._$litDirective$;return r?.constructor!==i&&(r?._$AO?.(!1),i===void 0?r=void 0:(r=new i(o),r._$AT(o,e,n)),n!==void 0?(e._$Co??=[])[n]=r:e._$Cl=r),r!==void 0&&(t=M(o,r._$AS(o,t.values),r,n)),t}var ct=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:n}=this._$AD,r=(t?.creationScope??k).importNode(e,!0);S.currentNode=r;let i=S.nextNode(),s=0,a=0,c=n[0];for(;c!==void 0;){if(s===c.index){let u;c.type===2?u=new F(i,i.nextSibling,this,t):c.type===1?u=new c.ctor(i,c.name,c.strings,this,t):c.type===6&&(u=new pt(i,this,t)),this._$AV.push(u),c=n[++a]}s!==c?.index&&(i=S.nextNode(),s++)}return S.currentNode=k,r}p(t){let e=0;for(let n of this._$AV)n!==void 0&&(n.strings!==void 0?(n._$AI(t,n,e),e+=n.strings.length-2):n._$AI(t[e])),e++}},F=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,n,r){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=n,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode,e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=M(this,t,e),U(t)?t===p||t==null||t===""?(this._$AH!==p&&this._$AR(),this._$AH=p):t!==this._$AH&&t!==P&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):re(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==p&&U(this._$AH)?this._$AA.nextSibling.data=t:this.T(k.createTextNode(t)),this._$AH=t}$(t){let{values:e,_$litType$:n}=t,r=typeof n=="number"?this._$AC(t):(n.el===void 0&&(n.el=N.createElement(Ot(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===r)this._$AH.p(e);else{let i=new ct(r,this),s=i.u(this.options);i.p(e),this.T(s),this._$AH=i}}_$AC(t){let e=Mt.get(t.strings);return e===void 0&&Mt.set(t.strings,e=new N(t)),e}k(t){mt(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,n,r=0;for(let i of t)r===e.length?e.push(n=new o(this.O(I()),this.O(I()),this,this.options)):n=e[r],n._$AI(i),r++;r<e.length&&(this._$AR(n&&n._$AB.nextSibling,r),e.length=r)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){let n=At(t).nextSibling;At(t).remove(),t=n}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}},L=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,n,r,i){this.type=1,this._$AH=p,this._$AN=void 0,this.element=t,this.name=e,this._$AM=r,this.options=i,n.length>2||n[0]!==""||n[1]!==""?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=p}_$AI(t,e=this,n,r){let i=this.strings,s=!1;if(i===void 0)t=M(this,t,e,0),s=!U(t)||t!==this._$AH&&t!==P,s&&(this._$AH=t);else{let a=t,c,u;for(t=i[0],c=0;c<i.length-1;c++)u=M(this,a[n+c],e,c),u===P&&(u=this._$AH[c]),s||=!U(u)||u!==this._$AH[c],u===p?t=p:t!==p&&(t+=(u??"")+i[c+1]),this._$AH[c]=u}s&&!r&&this.j(t)}j(t){t===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},lt=class extends L{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===p?void 0:t}},dt=class extends L{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==p)}},ut=class extends L{constructor(t,e,n,r,i){super(t,e,n,r,i),this.type=5}_$AI(t,e=this){if((t=M(this,t,e,0)??p)===P)return;let n=this._$AH,r=t===p&&n!==p||t.capture!==n.capture||t.once!==n.once||t.passive!==n.passive,i=t!==p&&(n===p||r);r&&this.element.removeEventListener(this.name,this,n),i&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},pt=class{constructor(t,e,n){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(t){M(this,t)}};var ie=ht.litHtmlPolyfillSupport;ie?.(N,F),(ht.litHtmlVersions??=[]).push("3.3.3");var Tt=(o,t,e)=>{let n=e?.renderBefore??t,r=n._$litPart$;if(r===void 0){let i=e?.renderBefore??null;n._$litPart$=r=new F(t.insertBefore(I(),i),i,void 0,e??{})}return r._$AI(o),r};var _t=globalThis,y=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=Tt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return P}};y._$litElement$=!0,y.finalized=!0,_t.litElementHydrateSupport?.({LitElement:y});var se=_t.litElementPolyfillSupport;se?.({LitElement:y});(_t.litElementVersions??=[]).push("4.2.2");function ae(o,t,e){return Math.min(Math.max(o,t),e)}function J(o,t,e){return e<=t?.5:ae((o-t)/(e-t),0,1)}function ce(o,t,e){if(o==null)return"unknown";if(o<t)return"below";if(o>e)return"above";let n=e-t;if(n<=0)return"in_band";let r=(o-t)/n;return r<.25?"cool_edge":r>.75?"warm_edge":"in_band"}function Dt(o){let{operative:t,setpoint:e,low:n,high:r}=o;if(n==null||r==null||r<=n)return null;let i=n-1.5,s=r+1.5;return{low:n,high:r,span:r-n,operative:t,setpoint:e,category:o.category??"",verdict:ce(t,n,r),axisLow:i,axisHigh:s,lowFrac:J(n,i,s),highFrac:J(r,i,s),operativeFrac:t==null?null:J(t,i,s),setpointFrac:e==null?null:J(e,i,s)}}var It={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function V(o){return It[o]??It.unknown}var le=[1e3,2e3],de=[30,40,60,65],ue=[26,30],pe=420,he=[800,1350];function _(o){return typeof o=="number"&&Number.isFinite(o)}function Z(o,t){return o&&o.length>=2&&_(o[0])&&_(o[1])&&o[0]<o[1]?[o[0],o[1]]:[t[0],t[1]]}function me(o,t){if(o&&o.length>=4&&o.slice(0,4).every(_)){let[e,n,r,i]=o;if(e<=n&&n<=r&&r<=i)return[e,n,r,i]}return[t[0],t[1],t[2],t[3]]}function fe(o){if(o?.scheme==="en16798"){let t=_(o.outdoor)?o.outdoor:pe,e=Z(o.enRise,he);return[t+e[0],t+e[1]]}return Z(o?.thresholds,le)}function _e(o,t){if(!_(o))return"unknown";let[e,n]=fe(t);return o>=n?"alert":o>=e?"warn":"ok"}function ge(o,t){if(!_(o))return"unknown";let[e,n,r,i]=me(t,de);return o<e||o>=i?"alert":o<n||o>r?"warn":"ok"}function be(o){switch(o){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function ve(o,t){if(!_(o))return"unknown";let[e,n]=Z(t,ue);return o>n?"alert":o>e?"warn":"ok"}var ye=[10,15];function $e(o){return 100-95*Math.exp(-(.03353*o**4+.2179*o**2))}function xe(o,t,e){let[n,r]=Z(e,ye),i=_(t)?t:_(o)?$e(o):null;return i==null?"unknown":i>=r?"alert":i>=n?"warn":"ok"}var we=[.5,1],Ae=[3,6],Ce=[85,60];function Nt(o){return o<=1?o*100:o}var Ut={unknown:-1,ok:0,warn:1,alert:2};function Ee(o){let t=[];if(_(o.deviationK)){let[e,n]=we;t.push(o.deviationK>=n?"alert":o.deviationK>=e?"warn":"ok")}if(_(o.cyclesPerH)){let[e,n]=Ae;t.push(o.cyclesPerH>=n?"alert":o.cyclesPerH>=e?"warn":"ok")}if(_(o.timeInBand)){let e=Nt(o.timeInBand),[n,r]=Ce;t.push(e<r?"alert":e<n?"warn":"ok")}return t.length?t.reduce((e,n)=>Ut[n]>Ut[e]?n:e,"ok"):"unknown"}function Ft(o,t){let e=[],n=t?.temperature_scale==="asr_office"?ve(o.temperature,t.asr_thresholds):be(o.comfortVerdict??null);if(e.push({key:"temperature",value:o.temperature,unit:"\xB0C",level:n,color:V(n)}),_(o.humidity)){let i=ge(o.humidity,t?.humidity_thresholds);e.push({key:"humidity",value:o.humidity,unit:"%",level:i,color:V(i)})}if(_(o.co2)){let i=_e(o.co2,{scheme:t?.co2_scheme,thresholds:t?.co2_thresholds,outdoor:t?.outdoor_co2});e.push({key:"co2",value:o.co2,unit:"ppm",level:i,color:V(i)})}if(_(o.pmv)||_(o.ppd)){let i=xe(o.pmv??null,o.ppd??null);e.push({key:"pmv",value:_(o.ppd)?o.ppd:null,unit:"%",level:i,color:V(i)})}let r=o.ca;if(r&&(_(r.deviationK)||_(r.timeInBand)||_(r.cyclesPerH))){let i=Ee(r);e.push({key:"ca",value:_(r.timeInBand)?Nt(r.timeInBand):null,unit:"%",level:i,color:V(i)})}return e}var Vt={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",override_clamped:"Setpoint clamped",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical"},Se={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",override_clamped:"Sollwert geklemmt",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch"};function d(o,t){return((o??"en").toLowerCase().startsWith("de")?Se:Vt)[t]??Vt[t]??t}var ke=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"show_shadow",selector:{boolean:{}}},{name:"compact",selector:{boolean:{}}}],Q=class extends y{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${ke}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};Q.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",Q);var tt="0.137.0",zt=!1;function Pe(){let o=()=>location.reload();"caches"in window?caches.keys().then(t=>Promise.all(t.map(e=>caches.delete(e)))).then(o,o):o()}async function et(o,t){if(!(zt||!t?.connection)){zt=!0;try{let e=await t.connection.sendMessagePromise({type:"poise/card_version"});if(e?.version&&e.version!==tt){let n=t.locale?.language;o.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${d(n,"update_msg")} (${tt} \u2192 ${e.version})`,duration:-1,dismissable:!0,action:{text:d(n,"reload"),action:Pe}},bubbles:!0,composed:!0}))}}catch{}}}function z(o){let t=typeof o=="string"?parseFloat(o):o;return typeof t=="number"&&!Number.isNaN(t)?t:null}var B=class extends y{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(t){return{type:"custom:poise-system-card",entity:Object.keys(t.states).find(n=>n.startsWith("binary_sensor.")&&t.states[n].attributes.zone_count!==void 0)??""}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config=t}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&et(this,this.hass)}shouldUpdate(t){if(t.has("_config"))return!0;let e=t.get("hass");return!e||!this._config?.entity?!0:e.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}render(){let t=this.hass?.locale?.language,e=this._config?.entity,n=e?this.hass.states[e]:void 0;if(!n)return m`<ha-card
        ><div class="empty">${d(t,"no_system")}</div></ha-card
      >`;let r=n.attributes,i=n.state==="on",s=z(r.flow_target),a=z(r.shed_count)??0,c=r.source_grants??{},u=Object.keys(c);return m`<ha-card .header=${d(t,"sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${d(t,"details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${i?"on":""}">
          <ha-icon icon=${i?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${i?d(t,"demand_on"):d(t,"demand_off")}</span>
          ${r.frost_override?m`<em class="frost">${d(t,"frost")}</em>`:p}
        </div>
        <div class="stats">
          <div>
            <strong>${z(r.active_zones)??0}</strong
            ><span>${d(t,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${z(r.controlling_zones)??0}/${z(r.zone_count)??0}</strong
            ><span>${d(t,"zones")}</span>
          </div>
          ${s!=null?m`<div>
                <strong>${s.toFixed(0)}°</strong><span>${d(t,"flow")}</span>
              </div>`:p}
          ${a>0?m`<div>
                <strong>${a}</strong><span>${d(t,"shed")}</span>
              </div>`:p}
        </div>
        ${u.length?m`<div class="grants">
              ${u.map(f=>m`<span class="chip">${f}: ${c[f]}</span>`)}
            </div>`:p}
      </div>
    </ha-card>`}};B.properties={hass:{},_config:{state:!0}},B.styles=O`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .wrap:focus { outline: none; }
    .wrap:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: -2px; border-radius: 10px;
    }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;var nt=class extends y{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};nt.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",nt);customElements.get("poise-system-card")||customElements.define("poise-system-card",B);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function Bt(o,t,e){return Math.min(Math.max(o,t),e)}function Kt(o,t,e,n=300,r=90,i=1){let s=[];for(let g of o)g.op!=null&&s.push(g.op),g.sp!=null&&s.push(g.sp);if(t!=null&&s.push(t),e!=null&&s.push(e),s.length===0||o.length===0)return null;let a=Math.min(...s)-i,c=Math.max(...s)+i,u=o[0].t,h=o[o.length-1].t-u||1,b=c-a||1,$=g=>(g-u)/h*n,x=g=>r-(g-a)/b*r,R=g=>o.filter(C=>g(C)!=null).map(C=>`${$(C.t).toFixed(1)},${x(g(C)).toFixed(1)}`).join(" ");return{width:n,height:r,opPath:R(g=>g.op),spPath:R(g=>g.sp),bandTop:e==null?0:Bt(x(e),0,r),bandBottom:t==null?r:Bt(x(t),0,r),vMin:a,vMax:c}}var v={min:16,max:28,start:135,sweep:270};function jt(o,t,e){return Math.min(Math.max(o,t),e)}function j(o,t=v){let e=jt((o-t.min)/(t.max-t.min),0,1);return t.start+e*t.sweep}function Me(o,t=v){let e=o;for(;e<t.start;)e+=360;for(;e>=t.start+360;)e-=360;if(e<=t.start+t.sweep)return e;let n=e-(t.start+t.sweep);return t.start+360-e<n?t.start:t.start+t.sweep}function Le(o,t=v){let n=(Me(o,t)-t.start)/t.sweep;return t.min+n*(t.max-t.min)}function K(o,t,e,n){let r=n*Math.PI/180;return{x:o+e*Math.cos(r),y:t+e*Math.sin(r)}}function gt(o,t,e,n,r){if(r<=n)return"";let i=K(o,t,e,n),s=K(o,t,e,r),a=r-n>180?1:0;return`M ${i.x.toFixed(2)} ${i.y.toFixed(2)} A ${e} ${e} 0 ${a} 1 ${s.x.toFixed(2)} ${s.y.toFixed(2)}`}function qt(o,t,e=v){let n=Math.atan2(t,o)*180/Math.PI;return n<0&&(n+=360),Le(n,e)}function Wt(o,t,e,n=v){let r;switch(o){case"ArrowUp":case"ArrowRight":r=t+e;break;case"ArrowDown":case"ArrowLeft":r=t-e;break;case"PageUp":r=t+e*5;break;case"PageDown":r=t-e*5;break;case"Home":r=n.min;break;case"End":r=n.max;break;default:return null}return Math.round(jt(r,n.min,n.max)/e)*e}function Re(o){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[o]??"mdi:tune"}function l(o){let t=typeof o=="string"?parseFloat(o):o;return typeof t=="number"&&!Number.isNaN(t)?t:null}var q=class extends y{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=v}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(e){return{type:"custom:poise-card",entity:Object.keys(e.states).find(r=>r.startsWith("climate.")&&e.states[r].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(e){if(!e)throw new Error("Invalid configuration");if(e.entity&&!e.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...e}}getCardSize(){return 4}getGridOptions(){return this._config?.compact?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(e){if(this._dragging||e.has("_config"))return!0;let n=e.get("hass");return!n||!this._config?.entity?!0:n.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(e){let n=this._config.entity;if(!n||!this.hass)return;let r=this.hass.states[n];if(!r)return;let i=l(r.attributes.target_temperature_step)??.5,s=l(r.attributes.heat_sp)??l(r.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:n,temperature:Math.round((s+e*i)*10)/10})}updated(){this.hass&&et(this,this.hass);let e=this._config?.entity;e&&this.hass&&this._histFor!==e&&(this._histFor=e,this._loadHistory(e))}async _loadHistory(e){if(!this.hass.connection)return;let n=new Date,r=new Date(n.getTime()-24*3600*1e3);try{let s=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:r.toISOString(),end_time:n.toISOString(),entity_ids:[e],minimal_response:!1,no_attributes:!1}))?.[e]??[],a={},c=[];for(let u of s){u.a&&(a={...a,...u.a});let f=(l(u.lu)??l(u.lc)??0)*1e3;c.push({t:f,op:l(a.operative_temperature)??l(a.current_temperature),sp:l(a.heat_sp)??l(a.temperature)})}this._history=c,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(e,n){let r=Kt(this._history,e,n,300,80);return r?m`<svg
      class="chart"
      viewBox="0 0 ${r.width} ${r.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${r.bandTop}
        width=${r.width}
        height=${Math.max(0,r.bandBottom-r.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${r.spPath} class="csp"></polyline>
      <polyline points=${r.opPath} class="cop"></polyline>
    </svg>`:p}render(){let e=this.hass?.locale?.language,n=this._config?.entity,r=n?this.hass.states[n]:void 0;if(!r)return m`<ha-card
        ><div class="empty">${d(e,"no_entity")}</div></ha-card
      >`;let i=r.attributes,s=l(i.operative_temperature)??l(i.current_temperature),a=l(i.heat_sp)??l(i.temperature),c=Dt({operative:s,setpoint:a,low:l(i.comfort_low),high:l(i.comfort_high),category:i.category??null});return m`<ha-card .header=${i.friendly_name??"Poise"}>
      <div class="wrap ${this._config.compact?"compact":""}">
        ${this._dial(i,e)}
        <div class="verdict">
          ${c?d(e,c.verdict):d(e,"unknown")}
          ${c?.category?m`<span class="cat">Kat. ${c.category}</span>`:p}
        </div>
        ${this._config.compact?p:m`${this._control(this._pending??a,e)}
              ${this._chart(l(i.comfort_low),l(i.comfort_high))}
              ${this._monitor(i,c,e)}
              ${this._chips(i,e)}`}
        ${this._learn(i,e)}
      </div>
    </ha-card>`}_dial(e,n){let r=l(e.operative_temperature)??l(e.current_temperature),i=l(e.heat_sp)??l(e.temperature),s={min:l(e.min_temp)??v.min,max:l(e.max_temp)??v.max,start:v.start,sweep:v.sweep};this._dialCfg=s.max>s.min?s:v;let a=this._pending??i??r??this._dialCfg.min,c=l(e.comfort_low),u=l(e.comfort_high),f=100,h=100,b=80,$=gt(f,h,b,v.start,v.start+v.sweep),x=c!=null&&u!=null?gt(f,h,b,j(Math.min(c,u),this._dialCfg),j(Math.max(c,u),this._dialCfg)):"",R=String(e.hvac_action??""),g=R==="heating"?"heat":R==="cooling"?"cool":"",C=K(f,h,b,j(a,this._dialCfg)),rt=r!=null?K(f,h,b,j(r,this._dialCfg)):null;return m`<div class="dialwrap">
      <svg
        class="dial"
        viewBox="0 0 200 200"
        role="slider"
        tabindex="0"
        aria-label=${d(n,"setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${a}
        aria-valuetext="${a.toFixed(1)} °C"
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${$}></path>
        <path class="bandarc" d=${x}></path>
        <circle
          class="opdot"
          cx=${(rt?.x??0).toFixed(1)}
          cy=${(rt?.y??0).toFixed(1)}
          r=${rt?5:0}
        ></circle>
        <circle class="handle ${g}" cx=${C.x.toFixed(1)} cy=${C.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div
          class="ctrclick"
          role="button"
          tabindex="0"
          aria-label=${d(n,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op">${r!=null?r.toFixed(1):"\u2014"}<span>°C</span></div>
          <div class="soll">${d(n,"setpoint")} <b>${a.toFixed(1)}°</b></div>
        </div>
      </div>
    </div>`}_fromPointer(e,n){let r=n.getBoundingClientRect();if(!r.width||!this._config.entity)return;let i=(e.clientX-r.left)/r.width*200-100,s=(e.clientY-r.top)/r.height*200-100,a=l(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(qt(i,s,this._dialCfg)/a)*a,this.requestUpdate()}_onDown(e){if(!this._config.entity)return;e.preventDefault();let n=e.currentTarget;n.setPointerCapture(e.pointerId),this._dragging=!0,this._fromPointer(e,n)}_onMove(e){this._dragging&&this._fromPointer(e,e.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let e=this._pending;this._pending=null,e!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:e}),this.requestUpdate()}_onKey(e){let n=this._config.entity;if(!n)return;let r=this.hass.states[n];if(!r)return;let i=l(r.attributes.target_temperature_step)??.5,s=l(r.attributes.heat_sp)??l(r.attributes.temperature)??this._dialCfg.min,a=Wt(e.key,s,i,this._dialCfg);a!=null&&(e.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:n,temperature:a}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}_control(e,n){return m`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${d(n,"setpoint")}</span
        ><strong>${e!=null?e.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_chips(e,n){let r=[];e.preheating&&r.push(this._chip("mdi:fire-circle",d(n,"preheating"),e.minutes_to_comfort,n)),e.coasting&&r.push(this._chip("mdi:coffee",d(n,"coasting"),e.minutes_to_setback,n)),e.window_open&&r.push(this._chip("mdi:window-open",d(n,e.window_auto_detected?"window_auto":"window"))),e.window_bypass&&r.push(this._chip("mdi:window-closed-variant",d(n,"bypass")));let i=e.preset==null?"none":String(e.preset);i!=="none"&&r.push(this._chip(Re(i),d(n,i)||i)),e.heating_failure&&r.push(this._chip("mdi:alert",d(n,"failure"))),e.override_clamped&&r.push(this._chip("mdi:arrow-collapse-vertical",d(n,"override_clamped")));let s=e.binding_lower_cause;return s&&s!=="en16798"&&r.push(this._chip("mdi:shield-alert",String(s))),r.length?m`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${d(n,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${r}
        </div>`:p}_chip(e,n,r,i){let s=l(r);return m`<div class="chip">
      <ha-icon icon=${e}></ha-icon><span>${n}</span>
      ${s!=null?m`<em>${Math.round(s)} ${d(i,"min_left")}</em>`:p}
    </div>`}_monitor(e,n,r){let i=Ft({temperature:l(e.operative_temperature)??l(e.current_temperature),comfortVerdict:n?.verdict??null,humidity:l(e.humidity)??l(e.current_humidity),co2:l(e.co2)??l(e.carbon_dioxide),pmv:l(e.pmv),ppd:l(e.ppd),ca:{deviationK:l(e.ca_deviation_k),timeInBand:l(e.ca_time_in_band),cyclesPerH:l(e.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:l(e.outdoor_co2)});return i.length>1||this._config.temperature_scale==="asr_office"?m`<div
      class="monitor"
      role="group"
      aria-label=${d(r,"air_quality")}
    >
      ${i.map(a=>this._lamp(a,r))}
    </div>`:p}_lamp(e,n){let r=d(n,e.key),i=d(n,e.level==="unknown"?"unknown":"air_"+e.level),s="\u2014";e.value!=null&&(s=e.key==="temperature"?e.value.toFixed(1):String(Math.round(e.value)));let a=`${r}: ${s} ${e.unit} \u2014 ${i}`;return m`<div class="lamp" title=${a} aria-label=${a}>
      <span class="dot" style="background:${e.color}"></span>
      <span class="lk">${r}</span>
      <span class="lv">${s}<small>${e.unit}</small></span>
    </div>`}_learn(e,n){let r=l(e.confidence),i=this._config.show_shadow&&(e.mpc_active||e.tpi_active||e.pi_active),s=l(e.pi_setpoint),a=l(e.mpc_setpoint),c=e.tpi_active?`TPI ${Math.round(l(e.tpi_valve_percent)??0)}%`:e.pi_active&&s!=null?`PI ${s.toFixed(1)}\xB0`:e.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return m`<div class="learn">
      ${r!=null?m`<div class="bar">
            <i style="width:${(r*100).toFixed(0)}%"></i>
          </div>
          <span>${d(n,"learning")} ${(r*100).toFixed(0)}%</span>`:p}
      ${i?m`<div class="pill">
            ${d(n,"shadow")}${c?m` · ${c}`:p}
          </div>`:p}
    </div>`}};q.properties={hass:{},_config:{state:!0}},q.styles=O`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .monitor { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 2px; }
    .lamp { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .lamp .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
    .lamp .lk { color: var(--secondary-text-color); }
    .lamp .lv { font-weight: 600; }
    .lamp .lv small { font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial:focus, .ctrclick:focus, .chips:focus { outline: none; }
    .dial:focus-visible, .ctrclick:focus-visible, .chips:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: 2px; border-radius: 10px;
    }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .ctrclick { pointer-events: auto; cursor: pointer; display: flex; flex-direction: column; align-items: center; }
    .handle.heat { fill: var(--state-climate-heat-color, #ff8100); }
    .handle.cool { fill: var(--state-climate-cool-color, #2b9af9); }
    .wrap.compact .dialwrap { max-width: 150px; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",q);console.info(`%c POISE-CARD ${tt} `,"background:#2196f3;color:#fff");export{q as PoiseCard};
