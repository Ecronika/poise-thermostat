/* poise-card 0.162.0 — bundled, served by the Poise integration (ADR-0040) */
var Z=globalThis,J=Z.ShadowRoot&&(Z.ShadyCSS===void 0||Z.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,he=Symbol(),Pe=new WeakMap,U=class{constructor(e,t,n){if(this._$cssResult$=!0,n!==he)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(J&&e===void 0){let n=t!==void 0&&t.length===1;n&&(e=Pe.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),n&&Pe.set(t,e))}return e}toString(){return this.cssText}},Me=o=>new U(typeof o=="string"?o:o+"",void 0,he),N=(o,...e)=>{let t=o.length===1?o[0]:e.reduce((n,r,s)=>n+(i=>{if(i._$cssResult$===!0)return i.cssText;if(typeof i=="number")return i;throw Error("Value passed to 'css' function must be a 'css' function result: "+i+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+o[s+1],o[0]);return new U(t,o,he)},Le=(o,e)=>{if(J)o.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let n=document.createElement("style"),r=Z.litNonce;r!==void 0&&n.setAttribute("nonce",r),n.textContent=t.cssText,o.appendChild(n)}},me=J?o=>o:o=>o instanceof CSSStyleSheet?(e=>{let t="";for(let n of e.cssRules)t+=n.cssText;return Me(t)})(o):o;var{is:ft,defineProperty:_t,getOwnPropertyDescriptor:gt,getOwnPropertyNames:bt,getOwnPropertySymbols:yt,getPrototypeOf:vt}=Object,Q=globalThis,He=Q.trustedTypes,xt=He?He.emptyScript:"",$t=Q.reactiveElementPolyfillSupport,F=(o,e)=>o,fe={toAttribute(o,e){switch(e){case Boolean:o=o?xt:null;break;case Object:case Array:o=o==null?o:JSON.stringify(o)}return o},fromAttribute(o,e){let t=o;switch(e){case Boolean:t=o!==null;break;case Number:t=o===null?null:Number(o);break;case Object:case Array:try{t=JSON.parse(o)}catch{t=null}}return t}},Te=(o,e)=>!ft(o,e),Re={attribute:!0,type:String,converter:fe,reflect:!1,useDefault:!1,hasChanged:Te};Symbol.metadata??=Symbol("metadata"),Q.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Re){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let n=Symbol(),r=this.getPropertyDescriptor(e,n,t);r!==void 0&&_t(this.prototype,e,r)}}static getPropertyDescriptor(e,t,n){let{get:r,set:s}=gt(this.prototype,e)??{get(){return this[t]},set(i){this[t]=i}};return{get:r,set(i){let l=r?.call(this);s?.call(this,i),this.requestUpdate(e,l,n)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??Re}static _$Ei(){if(this.hasOwnProperty(F("elementProperties")))return;let e=vt(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(F("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(F("properties"))){let t=this.properties,n=[...bt(t),...yt(t)];for(let r of n)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[n,r]of t)this.elementProperties.set(n,r)}this._$Eh=new Map;for(let[t,n]of this.elementProperties){let r=this._$Eu(t,n);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let n=new Set(e.flat(1/0).reverse());for(let r of n)t.unshift(me(r))}else e!==void 0&&t.push(me(e));return t}static _$Eu(e,t){let n=t.attribute;return n===!1?void 0:typeof n=="string"?n:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let n of t.keys())this.hasOwnProperty(n)&&(e.set(n,this[n]),delete this[n]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Le(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,n){this._$AK(e,n)}_$ET(e,t){let n=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,n);if(r!==void 0&&n.reflect===!0){let s=(n.converter?.toAttribute!==void 0?n.converter:fe).toAttribute(t,n.type);this._$Em=e,s==null?this.removeAttribute(r):this.setAttribute(r,s),this._$Em=null}}_$AK(e,t){let n=this.constructor,r=n._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let s=n.getPropertyOptions(r),i=typeof s.converter=="function"?{fromAttribute:s.converter}:s.converter?.fromAttribute!==void 0?s.converter:fe;this._$Em=r;let l=i.fromAttribute(t,s.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(e,t,n,r=!1,s){if(e!==void 0){let i=this.constructor;if(r===!1&&(s=this[e]),n??=i.getPropertyOptions(e),!((n.hasChanged??Te)(s,t)||n.useDefault&&n.reflect&&s===this._$Ej?.get(e)&&!this.hasAttribute(i._$Eu(e,n))))return;this.C(e,t,n)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:n,reflect:r,wrapped:s},i){n&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,i??t??this[e]),s!==!0||i!==void 0)||(this._$AL.has(e)||(this.hasUpdated||n||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,s]of this._$Ep)this[r]=s;this._$Ep=void 0}let n=this.constructor.elementProperties;if(n.size>0)for(let[r,s]of n){let{wrapped:i}=s,l=this[r];i!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,s,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(n=>n.hostUpdate?.()),this.update(t)):this._$EM()}catch(n){throw e=!1,this._$EM(),n}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[F("elementProperties")]=new Map,w[F("finalized")]=new Map,$t?.({ReactiveElement:w}),(Q.reactiveElementVersions??=[]).push("2.1.2");var $e=globalThis,Oe=o=>o,ee=$e.trustedTypes,De=ee?ee.createPolicy("lit-html",{createHTML:o=>o}):void 0,ze="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,Be="?"+C,wt=`<${Be}>`,P=document,z=()=>P.createComment(""),B=o=>o===null||typeof o!="object"&&typeof o!="function",we=Array.isArray,Ct=o=>we(o)||typeof o?.[Symbol.iterator]=="function",_e=`[ 	
\f\r]`,V=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ie=/-->/g,Ue=/>/g,k=RegExp(`>|${_e}(?:([^\\s"'>=/]+)(${_e}*=${_e}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Ne=/'/g,Fe=/"/g,Ke=/^(?:script|style|textarea|title)$/i,Ce=o=>(e,...t)=>({_$litType$:o,strings:e,values:t}),m=Ce(1),je=Ce(2),cn=Ce(3),M=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),Ve=new WeakMap,E=P.createTreeWalker(P,129);function qe(o,e){if(!we(o)||!o.hasOwnProperty("raw"))throw Error("invalid template strings array");return De!==void 0?De.createHTML(e):e}var At=(o,e)=>{let t=o.length-1,n=[],r,s=e===2?"<svg>":e===3?"<math>":"",i=V;for(let l=0;l<t;l++){let a=o[l],u,f,h=-1,g=0;for(;g<a.length&&(i.lastIndex=g,f=i.exec(a),f!==null);)g=i.lastIndex,i===V?f[1]==="!--"?i=Ie:f[1]!==void 0?i=Ue:f[2]!==void 0?(Ke.test(f[2])&&(r=RegExp("</"+f[2],"g")),i=k):f[3]!==void 0&&(i=k):i===k?f[0]===">"?(i=r??V,h=-1):f[1]===void 0?h=-2:(h=i.lastIndex-f[2].length,u=f[1],i=f[3]===void 0?k:f[3]==='"'?Fe:Ne):i===Fe||i===Ne?i=k:i===Ie||i===Ue?i=V:(i=k,r=void 0);let x=i===k&&o[l+1].startsWith("/>")?" ":"";s+=i===V?a+wt:h>=0?(n.push(u),a.slice(0,h)+ze+a.slice(h)+C+x):a+C+(h===-2?l:x)}return[qe(o,s+(o[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),n]},K=class o{constructor({strings:e,_$litType$:t},n){let r;this.parts=[];let s=0,i=0,l=e.length-1,a=this.parts,[u,f]=At(e,t);if(this.el=o.createElement(u,n),E.currentNode=this.el.content,t===2||t===3){let h=this.el.content.firstChild;h.replaceWith(...h.childNodes)}for(;(r=E.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let h of r.getAttributeNames())if(h.endsWith(ze)){let g=f[i++],x=r.getAttribute(h).split(C),$=/([.?@])?(.*)/.exec(g);a.push({type:1,index:s,name:$[2],strings:x,ctor:$[1]==="."?be:$[1]==="?"?ye:$[1]==="@"?ve:R}),r.removeAttribute(h)}else h.startsWith(C)&&(a.push({type:6,index:s}),r.removeAttribute(h));if(Ke.test(r.tagName)){let h=r.textContent.split(C),g=h.length-1;if(g>0){r.textContent=ee?ee.emptyScript:"";for(let x=0;x<g;x++)r.append(h[x],z()),E.nextNode(),a.push({type:2,index:++s});r.append(h[g],z())}}}else if(r.nodeType===8)if(r.data===Be)a.push({type:2,index:s});else{let h=-1;for(;(h=r.data.indexOf(C,h+1))!==-1;)a.push({type:7,index:s}),h+=C.length-1}s++}}static createElement(e,t){let n=P.createElement("template");return n.innerHTML=e,n}};function H(o,e,t=o,n){if(e===M)return e;let r=n!==void 0?t._$Co?.[n]:t._$Cl,s=B(e)?void 0:e._$litDirective$;return r?.constructor!==s&&(r?._$AO?.(!1),s===void 0?r=void 0:(r=new s(o),r._$AT(o,t,n)),n!==void 0?(t._$Co??=[])[n]=r:t._$Cl=r),r!==void 0&&(e=H(o,r._$AS(o,e.values),r,n)),e}var ge=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:n}=this._$AD,r=(e?.creationScope??P).importNode(t,!0);E.currentNode=r;let s=E.nextNode(),i=0,l=0,a=n[0];for(;a!==void 0;){if(i===a.index){let u;a.type===2?u=new j(s,s.nextSibling,this,e):a.type===1?u=new a.ctor(s,a.name,a.strings,this,e):a.type===6&&(u=new xe(s,this,e)),this._$AV.push(u),a=n[++l]}i!==a?.index&&(s=E.nextNode(),i++)}return E.currentNode=P,r}p(e){let t=0;for(let n of this._$AV)n!==void 0&&(n.strings!==void 0?(n._$AI(e,n,t),t+=n.strings.length-2):n._$AI(e[t])),t++}},j=class o{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,n,r){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=n,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=H(this,e,t),B(e)?e===p||e==null||e===""?(this._$AH!==p&&this._$AR(),this._$AH=p):e!==this._$AH&&e!==M&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):Ct(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==p&&B(this._$AH)?this._$AA.nextSibling.data=e:this.T(P.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:n}=e,r=typeof n=="number"?this._$AC(e):(n.el===void 0&&(n.el=K.createElement(qe(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===r)this._$AH.p(t);else{let s=new ge(r,this),i=s.u(this.options);s.p(t),this.T(i),this._$AH=s}}_$AC(e){let t=Ve.get(e.strings);return t===void 0&&Ve.set(e.strings,t=new K(e)),t}k(e){we(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,n,r=0;for(let s of e)r===t.length?t.push(n=new o(this.O(z()),this.O(z()),this,this.options)):n=t[r],n._$AI(s),r++;r<t.length&&(this._$AR(n&&n._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let n=Oe(e).nextSibling;Oe(e).remove(),e=n}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},R=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,n,r,s){this.type=1,this._$AH=p,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=s,n.length>2||n[0]!==""||n[1]!==""?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=p}_$AI(e,t=this,n,r){let s=this.strings,i=!1;if(s===void 0)e=H(this,e,t,0),i=!B(e)||e!==this._$AH&&e!==M,i&&(this._$AH=e);else{let l=e,a,u;for(e=s[0],a=0;a<s.length-1;a++)u=H(this,l[n+a],t,a),u===M&&(u=this._$AH[a]),i||=!B(u)||u!==this._$AH[a],u===p?e=p:e!==p&&(e+=(u??"")+s[a+1]),this._$AH[a]=u}i&&!r&&this.j(e)}j(e){e===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},be=class extends R{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===p?void 0:e}},ye=class extends R{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==p)}},ve=class extends R{constructor(e,t,n,r,s){super(e,t,n,r,s),this.type=5}_$AI(e,t=this){if((e=H(this,e,t,0)??p)===M)return;let n=this._$AH,r=e===p&&n!==p||e.capture!==n.capture||e.once!==n.once||e.passive!==n.passive,s=e!==p&&(n===p||r);r&&this.element.removeEventListener(this.name,this,n),s&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},xe=class{constructor(e,t,n){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(e){H(this,e)}};var St=$e.litHtmlPolyfillSupport;St?.(K,j),($e.litHtmlVersions??=[]).push("3.3.3");var We=(o,e,t)=>{let n=t?.renderBefore??e,r=n._$litPart$;if(r===void 0){let s=t?.renderBefore??null;n._$litPart$=r=new j(e.insertBefore(z(),s),s,void 0,t??{})}return r._$AI(o),r};var Ae=globalThis,v=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=We(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return M}};v._$litElement$=!0,v.finalized=!0,Ae.litElementHydrateSupport?.({LitElement:v});var kt=Ae.litElementPolyfillSupport;kt?.({LitElement:v});(Ae.litElementVersions??=[]).push("4.2.2");function Et(o,e,t){return Math.min(Math.max(o,e),t)}function te(o,e,t){return t<=e?.5:Et((o-e)/(t-e),0,1)}function Pt(o,e,t){if(o==null)return"unknown";if(o<e)return"below";if(o>t)return"above";let n=t-e;if(n<=0)return"in_band";let r=(o-e)/n;return r<.25?"cool_edge":r>.75?"warm_edge":"in_band"}function Ge(o){let{operative:e,setpoint:t,low:n,high:r}=o;if(n==null||r==null||r<=n)return null;let s=n-1.5,i=r+1.5;return{low:n,high:r,span:r-n,operative:e,setpoint:t,category:o.category??"",verdict:Pt(e,n,r),axisLow:s,axisHigh:i,lowFrac:te(n,s,i),highFrac:te(r,s,i),operativeFrac:e==null?null:te(e,s,i),setpointFrac:t==null?null:te(t,s,i)}}var Xe={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function q(o){return Xe[o]??Xe.unknown}var Mt=[1e3,2e3],Lt=[30,40,60,65],Ht=[26,30],Rt=420,Tt=[800,1350];function _(o){return typeof o=="number"&&Number.isFinite(o)}function ne(o,e){return o&&o.length>=2&&_(o[0])&&_(o[1])&&o[0]<o[1]?[o[0],o[1]]:[e[0],e[1]]}function Ot(o,e){if(o&&o.length>=4&&o.slice(0,4).every(_)){let[t,n,r,s]=o;if(t<=n&&n<=r&&r<=s)return[t,n,r,s]}return[e[0],e[1],e[2],e[3]]}function Dt(o){if(o?.scheme==="en16798"){let e=_(o.outdoor)?o.outdoor:Rt,t=ne(o.enRise,Tt);return[e+t[0],e+t[1]]}return ne(o?.thresholds,Mt)}function It(o,e){if(!_(o))return"unknown";let[t,n]=Dt(e);return o>=n?"alert":o>=t?"warn":"ok"}function Ut(o,e){if(!_(o))return"unknown";let[t,n,r,s]=Ot(e,Lt);return o<t||o>=s?"alert":o<n||o>r?"warn":"ok"}function Nt(o){switch(o){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function Ft(o,e){if(!_(o))return"unknown";let[t,n]=ne(e,Ht);return o>n?"alert":o>t?"warn":"ok"}var Vt=[10,15];function zt(o){return 100-95*Math.exp(-(.03353*o**4+.2179*o**2))}function Bt(o,e,t){let[n,r]=ne(t,Vt),s=_(e)?e:_(o)?zt(o):null;return s==null?"unknown":s>=r?"alert":s>=n?"warn":"ok"}var Kt=[.5,1],jt=[3,6],qt=[85,60];function Ze(o){return o<=1?o*100:o}var Ye={unknown:-1,ok:0,warn:1,alert:2};function Wt(o){let e=[];if(_(o.deviationK)){let[t,n]=Kt;e.push(o.deviationK>=n?"alert":o.deviationK>=t?"warn":"ok")}if(_(o.cyclesPerH)){let[t,n]=jt;e.push(o.cyclesPerH>=n?"alert":o.cyclesPerH>=t?"warn":"ok")}if(_(o.timeInBand)){let t=Ze(o.timeInBand),[n,r]=qt;e.push(t<r?"alert":t<n?"warn":"ok")}return e.length?e.reduce((t,n)=>Ye[n]>Ye[t]?n:t,"ok"):"unknown"}function Je(o,e){let t=[],n=e?.temperature_scale==="asr_office"?Ft(o.temperature,e.asr_thresholds):Nt(o.comfortVerdict??null);if(t.push({key:"temperature",value:o.temperature,unit:"\xB0C",level:n,color:q(n)}),_(o.humidity)){let s=Ut(o.humidity,e?.humidity_thresholds);t.push({key:"humidity",value:o.humidity,unit:"%",level:s,color:q(s)})}if(_(o.co2)){let s=It(o.co2,{scheme:e?.co2_scheme,thresholds:e?.co2_thresholds,outdoor:e?.outdoor_co2});t.push({key:"co2",value:o.co2,unit:"ppm",level:s,color:q(s)})}if(_(o.pmv)||_(o.ppd)){let s=Bt(o.pmv??null,o.ppd??null);t.push({key:"pmv",value:_(o.ppd)?o.ppd:null,unit:"%",level:s,color:q(s)})}let r=o.ca;if(r&&(_(r.deviationK)||_(r.timeInBand)||_(r.cyclesPerH))){let s=Wt(r);t.push({key:"ca",value:_(r.timeInBand)?Ze(r.timeInBand):null,unit:"%",level:s,color:q(s)})}return t}var Se=["hvac","window","temperature","humidity","co2","ca"],Gt=[12,24,48];function Qe(o,e,t){return typeof o=="string"&&e.includes(o)?o:t}function T(o,e){return typeof o=="boolean"?o:e}function Xt(o){return o===!1?new Set:o==null||o===!0?new Set(Se):Array.isArray(o)?new Set(o.filter(e=>Se.includes(e))):new Set(Se)}function Yt(o){if(o===!1)return{show:!1,hours:24};if(o===!0||o==null)return{show:!0,hours:24};let e=typeof o.hours=="number"?o.hours:Number(o.hours),t=Gt.includes(e)?e:24;return{show:T(o.show,!0),hours:t}}function et(o){let e=o.sections??{},t=o.density?Qe(o.density,["comfortable","compact"],"comfortable"):o.compact?"compact":"comfortable";return{entity:o.entity,density:t,controls:Qe(o.controls,["dial","buttons","none"],"dial"),history:Yt(o.history),chips:Xt(e.chips),shadowPill:T(e.shadow_pill,T(o.show_shadow,!0)),learning:T(e.learning,!0),pmv:T(e.pmv,!0),presets:T(e.presets,!0),temperature_scale:o.temperature_scale,humidity_thresholds:o.humidity_thresholds,co2_scheme:o.co2_scheme,co2_thresholds:o.co2_thresholds}}var tt={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",override_clamped:"Setpoint clamped",manual:"Manual",resume_schedule:"Resume schedule",valid_until:"valid until",instead_of:"instead of",norm_limit:"norm limit",permanent:"permanent",compressor_guard:"Compressor guard",mould:"Mould limit",presets:"Presets",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical"},Zt={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",override_clamped:"Sollwert geklemmt",manual:"Manuell",resume_schedule:"Zeitplan fortsetzen",valid_until:"gilt bis",instead_of:"statt",norm_limit:"Normgrenze",permanent:"dauerhaft",compressor_guard:"Verdichterschutz",mould:"Schimmelgrenze",presets:"Voreinstellungen",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch"};function d(o,e){return((o??"en").toLowerCase().startsWith("de")?Zt:tt)[e]??tt[e]??e}var Jt=[{value:"hvac",label:"HVAC status"},{value:"window",label:"Window"},{value:"temperature",label:"Temperature"},{value:"humidity",label:"Humidity"},{value:"co2",label:"CO\u2082"},{value:"ca",label:"Regulation (CA)"}],Qt=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}},{name:"controls",selector:{select:{mode:"dropdown",options:[{value:"dial",label:"Dial (drag)"},{value:"buttons",label:"Buttons (+/\u2212)"},{value:"none",label:"Display only"}]}}},{type:"expandable",name:"history",title:"History",schema:[{name:"show",selector:{boolean:{}}},{name:"hours",selector:{select:{mode:"dropdown",options:[{value:12,label:"12 h"},{value:24,label:"24 h"},{value:48,label:"48 h"}]}}}]},{type:"expandable",name:"sections",title:"Sections",schema:[{name:"chips",selector:{select:{multiple:!0,options:Jt}}},{name:"pmv",selector:{boolean:{}}},{name:"presets",selector:{boolean:{}}},{name:"shadow_pill",selector:{boolean:{}}},{name:"learning",selector:{boolean:{}}}]},{type:"expandable",name:"",title:"Advanced",flatten:!0,schema:[{name:"temperature_scale",selector:{select:{mode:"dropdown",options:[{value:"comfort",label:"Comfort band"},{value:"asr_office",label:"ASR office (\u226426 \xB0C)"}]}}},{name:"co2_scheme",selector:{select:{mode:"dropdown",options:[{value:"uba",label:"UBA (absolute)"},{value:"en16798",label:"EN 16798 (outdoor offset)"}]}}}]}],en={entity:"Entity",density:"Density",controls:"Controls",history:"History",sections:"Sections",show:"Show graph",hours:"Time span",chips:"Condition chips",pmv:"Comfort (PMV) lamp",presets:"Preset buttons",shadow_pill:"Shadow pill",learning:"Learning bar",temperature_scale:"Temperature scale",co2_scheme:"CO\u2082 scale"},oe=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${Qt}
      .computeLabel=${e=>en[e.name]??e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};oe.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",oe);var re="0.162.0",nt=!1;function tn(){let o=()=>location.reload();"caches"in window?caches.keys().then(e=>Promise.all(e.map(t=>caches.delete(t)))).then(o,o):o()}async function se(o,e){if(!(nt||!e?.connection)){nt=!0;try{let t=await e.connection.sendMessagePromise({type:"poise/card_version"});if(t?.version&&t.version!==re){let n=e.locale?.language;o.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${d(n,"update_msg")} (${re} \u2192 ${t.version})`,duration:-1,dismissable:!0,action:{text:d(n,"reload"),action:tn}},bubbles:!0,composed:!0}))}}catch{}}}function W(o){let e=typeof o=="string"?parseFloat(o):o;return typeof e=="number"&&!Number.isNaN(e)?e:null}var G=class extends v{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(e){return{type:"custom:poise-system-card",entity:Object.keys(e.states).find(n=>n.startsWith("binary_sensor.")&&e.states[n].attributes.zone_count!==void 0)??""}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&se(this,this.hass)}shouldUpdate(e){if(e.has("_config"))return!0;let t=e.get("hass");return!t||!this._config?.entity?!0:t.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}render(){let e=this.hass?.locale?.language,t=this._config?.entity,n=t?this.hass.states[t]:void 0;if(!n)return m`<ha-card
        ><div class="empty">${d(e,"no_system")}</div></ha-card
      >`;let r=n.attributes,s=n.state==="on",i=W(r.flow_target),l=W(r.shed_count)??0,a=r.source_grants??{},u=Object.keys(a);return m`<ha-card .header=${d(e,"sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${d(e,"details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${s?"on":""}">
          <ha-icon icon=${s?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${s?d(e,"demand_on"):d(e,"demand_off")}</span>
          ${r.frost_override?m`<em class="frost">${d(e,"frost")}</em>`:p}
        </div>
        <div class="stats">
          <div>
            <strong>${W(r.active_zones)??0}</strong
            ><span>${d(e,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${W(r.controlling_zones)??0}/${W(r.zone_count)??0}</strong
            ><span>${d(e,"zones")}</span>
          </div>
          ${i!=null?m`<div>
                <strong>${i.toFixed(0)}°</strong><span>${d(e,"flow")}</span>
              </div>`:p}
          ${l>0?m`<div>
                <strong>${l}</strong><span>${d(e,"shed")}</span>
              </div>`:p}
        </div>
        ${u.length?m`<div class="grants">
              ${u.map(f=>m`<span class="chip">${f}: ${a[f]}</span>`)}
            </div>`:p}
      </div>
    </ha-card>`}};G.properties={hass:{},_config:{state:!0}},G.styles=N`
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
  `;var ie=class extends v{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?m``:m`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${e=>e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};ie.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",ie);customElements.get("poise-system-card")||customElements.define("poise-system-card",G);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function ot(o,e,t){return Math.min(Math.max(o,e),t)}function rt(o,e,t,n=300,r=90,s=1){let i=[];for(let b of o)b.op!=null&&i.push(b.op),b.sp!=null&&i.push(b.sp);if(e!=null&&i.push(e),t!=null&&i.push(t),i.length===0||o.length===0)return null;let l=Math.min(...i)-s,a=Math.max(...i)+s,u=o[0].t,h=o[o.length-1].t-u||1,g=a-l||1,x=b=>(b-u)/h*n,$=b=>r-(b-l)/g*r,D=b=>o.filter(S=>b(S)!=null).map(S=>`${x(S.t).toFixed(1)},${$(b(S)).toFixed(1)}`).join(" ");return{width:n,height:r,opPath:D(b=>b.op),spPath:D(b=>b.sp),bandTop:t==null?0:ot($(t),0,r),bandBottom:e==null?r:ot($(e),0,r),vMin:l,vMax:a}}var y={min:16,max:28,start:135,sweep:270};function st(o,e,t){return Math.min(Math.max(o,e),t)}function O(o,e=y){let t=st((o-e.min)/(e.max-e.min),0,1);return e.start+t*e.sweep}function nn(o,e=y){let t=o;for(;t<e.start;)t+=360;for(;t>=e.start+360;)t-=360;if(t<=e.start+e.sweep)return t;let n=t-(e.start+e.sweep);return e.start+360-t<n?e.start:e.start+e.sweep}function on(o,e=y){let n=(nn(o,e)-e.start)/e.sweep;return e.min+n*(e.max-e.min)}function A(o,e,t,n){let r=n*Math.PI/180;return{x:o+t*Math.cos(r),y:e+t*Math.sin(r)}}function ke(o,e,t,n,r){if(r<=n)return"";let s=A(o,e,t,n),i=A(o,e,t,r),l=r-n>180?1:0;return`M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${t} ${t} 0 ${l} 1 ${i.x.toFixed(2)} ${i.y.toFixed(2)}`}function it(o,e,t=y){let n=Math.atan2(e,o)*180/Math.PI;return n<0&&(n+=360),on(n,t)}function at(o,e,t,n=y){let r;switch(o){case"ArrowUp":case"ArrowRight":r=e+t;break;case"ArrowDown":case"ArrowLeft":r=e-t;break;case"PageUp":r=e+t*5;break;case"PageDown":r=e-t*5;break;case"Home":r=n.min;break;case"End":r=n.max;break;default:return null}return Math.round(st(r,n.min,n.max)/t)*t}function Ee(o,e=Date.now()){if(typeof o!="string")return null;let t=Date.parse(o);return Number.isNaN(t)?null:Math.max(0,Math.round((t-e)/6e4))}function lt(o,e){if(typeof o!="string")return null;let t=Date.parse(o);return Number.isNaN(t)?null:new Date(t).toLocaleTimeString(e,{hour:"2-digit",minute:"2-digit"})}function ct(o,e,t,n,r=Date.now()){let s=d(o,"manual");return t==="permanent"?{label:`${s} (${d(o,"permanent")})`,minutes:null,permanent:!0}:{label:e!=null?`${s} ${e.toFixed(1)}\xB0`:s,minutes:Ee(n,r),permanent:!1}}function dt(o,e,t){return e==null||t==null?d(o,"override_clamped"):`${e.toFixed(1)}\xB0 ${d(o,"instead_of")} ${t.toFixed(1)}\xB0 (${d(o,"norm_limit")})`}function ut(o,e,t){let n=e==null?"none":String(e).toLowerCase();return n==="none"||t?null:{key:n,label:d(o,n)||n}}function pt(o,e){o.callService("poise","resume_schedule",{entity_id:e})}function ht(o){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[o]??"mdi:tune"}function c(o){let e=typeof o=="string"?parseFloat(o):o;return typeof e=="number"&&!Number.isNaN(e)?e:null}var X=class extends v{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=y}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(t){return{type:"custom:poise-card",entity:Object.keys(t.states).find(r=>r.startsWith("climate.")&&t.states[r].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(t){if(!t)throw new Error("Invalid configuration");if(t.entity&&!t.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...t},this._r=et(this._config)}getCardSize(){return 4}getGridOptions(){return this._r?.density==="compact"?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(t){if(this._dragging||t.has("_config"))return!0;let n=t.get("hass");return!n||!this._config?.entity?!0:n.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(t){let n=this._config.entity;if(!n||!this.hass)return;let r=this.hass.states[n];if(!r)return;let s=c(r.attributes.target_temperature_step)??.5,i=c(r.attributes.heat_sp)??c(r.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:n,temperature:Math.round((i+t*s)*10)/10})}updated(){this.hass&&se(this,this.hass);let t=this._config?.entity;t&&this.hass&&this._r?.history.show&&this._histFor!==t&&(this._histFor=t,this._loadHistory(t))}async _loadHistory(t){if(!this.hass.connection)return;let n=this._r?.history.hours??24,r=new Date,s=new Date(r.getTime()-n*3600*1e3);try{let l=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:s.toISOString(),end_time:r.toISOString(),entity_ids:[t],minimal_response:!1,no_attributes:!1}))?.[t]??[],a={},u=[];for(let f of l){f.a&&(a={...a,...f.a});let h=(c(f.lu)??c(f.lc)??0)*1e3;u.push({t:h,op:c(a.operative_temperature)??c(a.current_temperature),sp:c(a.heat_sp)??c(a.temperature)})}this._history=u,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(t,n){let r=rt(this._history,t,n,300,80);return r?m`<svg
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
    </svg>`:p}render(){let t=this.hass?.locale?.language,n=this._config?.entity,r=n?this.hass.states[n]:void 0;if(!r)return m`<ha-card
        ><div class="empty">${d(t,"no_entity")}</div></ha-card
      >`;let s=r.attributes,i=c(s.operative_temperature)??c(s.current_temperature),l=c(s.heat_sp)??c(s.temperature),a=Ge({operative:i,setpoint:l,low:c(s.comfort_low),high:c(s.comfort_high),category:s.category??null}),u=this._r;return m`<ha-card .header=${s.friendly_name??"Poise"}>
      <div class="wrap ${u.density==="compact"?"compact":""}">
        ${this._dial(s,t)}
        <div class="verdict">
          ${a?d(t,a.verdict):d(t,"unknown")}
          ${a?.category?m`<span class="cat">Kat. ${a.category}</span>`:p}
        </div>
        ${this._holdPill(s,t)}
        ${u.controls==="buttons"?this._control(this._pending??l,t):p}
        ${this._presets(s,t)}
        ${u.history.show?this._chart(c(s.comfort_low),c(s.comfort_high)):p}
        ${this._monitor(s,a,t)} ${this._chips(s,t)}
        ${this._learn(s,t)}
      </div>
    </ha-card>`}_dial(t,n){let r=c(t.operative_temperature)??c(t.current_temperature),s=c(t.heat_sp)??c(t.temperature),i={min:c(t.min_temp)??y.min,max:c(t.max_temp)??y.max,start:y.start,sweep:y.sweep};this._dialCfg=i.max>i.min?i:y;let l=this._pending??s??r??this._dialCfg.min,a=c(t.comfort_low),u=c(t.comfort_high),f=100,h=100,g=80,x=ke(f,h,g,y.start,y.start+y.sweep),$=a!=null&&u!=null?ke(f,h,g,O(Math.min(a,u),this._dialCfg),O(Math.max(a,u),this._dialCfg)):"",D=String(t.hvac_action??""),b=D==="heating"?"heat":D==="cooling"?"cool":"",S=A(f,h,g,O(l,this._dialCfg)),ae=r!=null?A(f,h,g,O(r,this._dialCfg)):null,L=c(t.mould_floor),I=L!=null&&L>this._dialCfg.min&&L<this._dialCfg.max,le=I?O(L,this._dialCfg):0,ce=I?A(f,h,g-9,le):null,de=I?A(f,h,g+9,le):null,ue=I?A(f,h,g+17,le):null,pe=this._r.controls==="dial",Y=this._dragging?lt(t.override_expires_at,n):null,mt=`${l.toFixed(1)} \xB0C${Y?` \xB7 ${d(n,"valid_until")} ${Y}`:""}`;return m`<div class="dialwrap">
      <svg
        class="dial ${pe?"":"ro"}"
        viewBox="0 0 200 200"
        role=${pe?"slider":"img"}
        tabindex=${pe?0:-1}
        aria-label=${d(n,"setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${l}
        aria-valuetext=${mt}
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${x}></path>
        <path class="bandarc" d=${$}></path>
        ${I&&ce&&de&&ue?je`<line class="mould" x1=${ce.x.toFixed(1)} y1=${ce.y.toFixed(1)} x2=${de.x.toFixed(1)} y2=${de.y.toFixed(1)}><title>${d(n,"mould")} ${L.toFixed(1)}°</title></line><text class="mlbl" x=${ue.x.toFixed(1)} y=${ue.y.toFixed(1)}>${L.toFixed(0)}°</text>`:p}
        <circle
          class="opdot"
          cx=${(ae?.x??0).toFixed(1)}
          cy=${(ae?.y??0).toFixed(1)}
          r=${ae?5:0}
        ></circle>
        <circle class="handle ${b}" cx=${S.x.toFixed(1)} cy=${S.y.toFixed(1)} r="9"></circle>
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
          <div class="soll">${d(n,"setpoint")} <b>${l.toFixed(1)}°</b></div>
          ${Y?m`<div class="valid">${d(n,"valid_until")} ${Y}</div>`:p}
        </div>
      </div>
    </div>`}_fromPointer(t,n){let r=n.getBoundingClientRect();if(!r.width||!this._config.entity)return;let s=(t.clientX-r.left)/r.width*200-100,i=(t.clientY-r.top)/r.height*200-100,l=c(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(it(s,i,this._dialCfg)/l)*l,this.requestUpdate()}_onDown(t){if(!this._config.entity||this._r.controls!=="dial")return;t.preventDefault();let n=t.currentTarget;n.setPointerCapture(t.pointerId),this._dragging=!0,this._fromPointer(t,n)}_onMove(t){this._dragging&&this._fromPointer(t,t.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let t=this._pending;this._pending=null,t!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:t}),this.requestUpdate()}_onKey(t){let n=this._config.entity;if(!n||this._r.controls!=="dial")return;let r=this.hass.states[n];if(!r)return;let s=c(r.attributes.target_temperature_step)??.5,i=c(r.attributes.heat_sp)??c(r.attributes.temperature)??this._dialCfg.min,l=at(t.key,i,s,this._dialCfg);l!=null&&(t.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:n,temperature:l}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}_control(t,n){return m`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${d(n,"setpoint")}</span
        ><strong>${t!=null?t.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_setPreset(t){let n=this._config.entity;!n||!this.hass||this.hass.callService("climate","set_preset_mode",{entity_id:n,preset_mode:t})}_resumeSchedule(){let t=this._config.entity;!t||!this.hass||pt(this.hass,t)}_presets(t,n){if(!this._r.presets)return p;let r=t.preset_modes;if(!Array.isArray(r)||!r.length)return p;let s=t.preset_mode==null?null:String(t.preset_mode),i=Ee(t.boost_expires_at);return m`<div class="presets" role="group" aria-label=${d(n,"presets")}>
      ${r.map(l=>{let a=String(l),u=a.toLowerCase();return m`<button
          class="preset ${s===a?"on":""}"
          aria-pressed=${s===a?"true":"false"}
          @click=${()=>this._setPreset(a)}
        >
          <ha-icon icon=${ht(u)}></ha-icon>
          <span>${d(n,u)||a}</span>
          ${u==="boost"&&i!=null?m`<em>${i} ${d(n,"min_left")}</em>`:p}
        </button>`})}
    </div>`}_holdPill(t,n){if(!t.override_active)return p;let r=c(t.heat_sp)??c(t.temperature),s=ct(n,r,t.override_policy,t.override_expires_at);return m`<div class="hold">
      <div class="chip hold-chip">
        <ha-icon icon="mdi:hand-back-right"></ha-icon><span>${s.label}</span>
        ${s.minutes!=null?m`<em>· ${s.minutes} ${d(n,"min_left")}</em>`:p}
      </div>
      <button
        class="resume"
        aria-label=${d(n,"resume_schedule")}
        title=${d(n,"resume_schedule")}
        @click=${this._resumeSchedule}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`}_chips(t,n){let r=this._r,s=[];if(r.chips.has("hvac")){t.preheating&&s.push(this._chip("mdi:fire-circle",d(n,"preheating"),t.minutes_to_comfort,n)),t.coasting&&s.push(this._chip("mdi:coffee",d(n,"coasting"),t.minutes_to_setback,n));let i=ut(n,t.preset,r.presets);i&&s.push(this._chip(ht(i.key),i.label)),t.heating_failure&&s.push(this._chip("mdi:alert",d(n,"failure"))),t.override_clamped&&s.push(this._chip("mdi:arrow-collapse-vertical",dt(n,c(t.heat_sp)??c(t.temperature),c(t.override_requested)))),t.mode_nudge_blocked&&s.push(this._chip("mdi:timer-sand",`${d(n,"compressor_guard")}: ${t.mode_nudge_blocked}`));let l=t.binding_lower_cause;l&&l!=="en16798"&&s.push(this._chip("mdi:shield-alert",String(l)))}return r.chips.has("window")&&(t.window_open&&s.push(this._chip("mdi:window-open",d(n,t.window_auto_detected?"window_auto":"window"))),t.window_bypass&&s.push(this._chip("mdi:window-closed-variant",d(n,"bypass")))),s.length?m`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${d(n,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${s}
        </div>`:p}_chip(t,n,r,s){let i=c(r);return m`<div class="chip">
      <ha-icon icon=${t}></ha-icon><span>${n}</span>
      ${i!=null?m`<em>${Math.round(i)} ${d(s,"min_left")}</em>`:p}
    </div>`}_monitor(t,n,r){let s=Je({temperature:c(t.operative_temperature)??c(t.current_temperature),comfortVerdict:n?.verdict??null,humidity:c(t.humidity)??c(t.current_humidity),co2:c(t.co2)??c(t.carbon_dioxide),pmv:c(t.pmv),ppd:c(t.ppd),ca:{deviationK:c(t.ca_deviation_k),timeInBand:c(t.ca_time_in_band),cyclesPerH:c(t.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:c(t.outdoor_co2)}),i=this._r,l=s.filter(a=>a.key==="pmv"?i.pmv:i.chips.has(a.key));return l.length?m`<div
      class="monitor"
      role="group"
      aria-label=${d(r,"air_quality")}
    >
      ${l.map(a=>this._lamp(a,r))}
    </div>`:p}_lamp(t,n){let r=d(n,t.key),s=d(n,t.level==="unknown"?"unknown":"air_"+t.level),i="\u2014";t.value!=null&&(i=t.key==="temperature"?t.value.toFixed(1):String(Math.round(t.value)));let l=`${r}: ${i} ${t.unit} \u2014 ${s}`;return m`<div class="lamp" title=${l} aria-label=${l}>
      <span class="dot" style="background:${t.color}"></span>
      <span class="lk">${r}</span>
      <span class="lv">${i}<small>${t.unit}</small></span>
    </div>`}_learn(t,n){let r=c(t.confidence),s=this._r.learning&&r!=null,i=this._r.shadowPill&&(t.mpc_active||t.tpi_active||t.pi_active);if(!s&&!i)return p;let l=c(t.pi_setpoint),a=c(t.mpc_setpoint),u=t.tpi_active?`TPI ${Math.round(c(t.tpi_valve_percent)??0)}%`:t.pi_active&&l!=null?`PI ${l.toFixed(1)}\xB0`:t.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return m`<div class="learn">
      ${s?m`<div class="bar">
            <i style="width:${((r??0)*100).toFixed(0)}%"></i>
          </div>
          <span>${d(n,"learning")} ${((r??0)*100).toFixed(0)}%</span>`:p}
      ${i?m`<div class="pill">
            ${d(n,"shadow")}${u?m` · ${u}`:p}
          </div>`:p}
    </div>`}};X.properties={hass:{},_config:{state:!0}},X.styles=N`
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
    .mould { stroke: var(--warning-color, #ff9800); stroke-width: 3; stroke-linecap: round; }
    .mlbl { fill: var(--warning-color, #ff9800); font-size: 11px; font-weight: 600;
      text-anchor: middle; dominant-baseline: middle; }
    .dial.ro { cursor: default; }
    .presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }
    .preset { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
      border: 1px solid var(--divider-color, #e0e0e0); border-radius: 16px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color); font: inherit; font-size: 13px; cursor: pointer; }
    .preset ha-icon { --mdc-icon-size: 16px; }
    .preset.on { background: var(--primary-color, #2196f3);
      color: var(--text-primary-color, #fff); border-color: var(--primary-color, #2196f3); }
    .preset:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .preset em { font-style: normal; color: var(--secondary-text-color); margin-left: 2px; }
    .preset.on em { color: inherit; opacity: 0.85; }
    .hold { display: flex; align-items: center; gap: 6px; margin: 8px 0 2px; }
    .hold-chip { flex: 1 1 auto; }
    .resume { flex: none; display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; padding: 0; border: none; border-radius: 50%;
      background: var(--secondary-background-color); color: var(--secondary-text-color); cursor: pointer; }
    .resume ha-icon { --mdc-icon-size: 18px; }
    .resume:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .valid { font-size: 11px; color: var(--secondary-text-color); margin-top: 3px; }
    .wrap.compact { padding: 6px 12px 12px; }
    .wrap.compact .dialctr .op { font-size: 30px; }
    .wrap.compact .presets, .wrap.compact .monitor, .wrap.compact .chips { gap: 4px; }
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",X);console.info(`%c POISE-CARD ${re} `,"background:#2196f3;color:#fff");export{X as PoiseCard};
